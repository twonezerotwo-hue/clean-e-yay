"""Persona/chat prompt'larına giren KOMPAKT state bağlamı.

Kural: full raw market data prompt'a gömülmez. Sadece karar zincirinin
özeti girer: DQS, provider durumu, decision matrix top hücreleri,
candidate vs final farkları, blocked_by, RiskGate, halt, korelasyon
cluster'ları, paper state, learning uyarıları, haber/katalizör başlıkları.

LLM bu bağlamı sadece OKUR — buradan decision/risk/paper akışına hiçbir
şey geri yazılmaz.
"""
from __future__ import annotations

import hashlib
import json
import re

from packages.data.ingestion.pipeline import (
    MarketSnapshot,
    get_cached_snapshot,
)
from packages.data.provenance import data_provenance
from packages.data.registry import assets as asset_registry
from packages.decision.engine import decide_matrix, matrix_view
from packages.learning import mistake_memory
from packages.paper import state as paper_state
from packages.risk import correlation
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

TOP_CELL_COUNT = 8


def _risk_input(ps: paper_state.PaperState, snap: MarketSnapshot) -> RiskInput:
    return RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )


def _deep_data_summary(view: dict, snap: MarketSnapshot) -> dict:
    """v2.7 deep-data (D2 türev / D3 options / D4 volatilite / D5 catalyst
    half-life / event riski) + rotation'ın KOMPAKT özeti.

    `matrix_view` bu dimensiyonları zaten yalnızca-dikkat-çeken (status OK +
    rejim/aksiyon kısıtlayıcı) olarak filtreliyor — persona/chat bağlamına
    olduğu gibi taşınır. LLM bunları yalnızca AÇIKLAR; karar zincirine geri
    yazılmaz. Etkilenen hücreler ayrıca matrix `blocked_by` ile zaten görünür.
    """
    options = [
        {
            "symbol": o["symbol"],
            "regime": o["regime"],
            "atm_iv": o["atm_iv"],
            "iv_rv_spread": o["iv_rv_spread"],
            "skew_25d": o["skew_25d"],
            "is_proxy": o.get("is_proxy", False),
        }
        for o in (view.get("options") or [])
    ]
    volatility = [
        {
            "symbol": v["symbol"],
            "timeframe": v["timeframe"],
            "regime": v["regime"],
            "vol_state": v["vol_state"],
            "vol_zscore": v["vol_zscore"],
        }
        for v in (view.get("volatility") or [])
    ]
    derivatives = [
        {
            "symbol": d["symbol"],
            "squeeze_level": d["squeeze_level"],
            "funding_bias": d["funding_bias"],
            "is_proxy": d.get("is_proxy", False),
        }
        for d in (view.get("derivatives") or [])
    ]
    catalysts = [
        {
            "event_type": c["event_type"],
            "actionability": c["actionability"],
            "affected_assets": list(c.get("affected_assets") or []),
            "affected_timeframes": list(c.get("affected_timeframes") or []),
            "half_life_minutes": c.get("expected_half_life_minutes"),
            "surprise_level": c.get("surprise_level"),
        }
        for c in (view.get("catalysts") or [])
    ]
    er = view.get("event_risk") or {}
    event_risk = {
        "level": er.get("level"),
        "action": er.get("action"),
        "restrictive": bool(er.get("restrictive")),
        "triggers": [
            {"title": t.get("title"), "level": t.get("level"),
             "importance": t.get("importance")}
            for t in (er.get("triggers") or [])
        ][:3],
    }
    rot = snap.rotation
    rotation = {
        "status": rot.status,
        "score": round(rot.score, 1),
        "direction": rot.direction,
        "evidence": list(rot.evidence)[:2],
    }
    return {
        "options": options,
        "volatility": volatility,
        "derivatives": derivatives,
        "catalysts": catalysts,
        "event_risk": event_risk,
        "rotation": rotation,
    }


# Momentum (RSI/MACD/EMA) ham yön — gate ÖNCESİ niyeti söylemek için (LLM
# "düşüş momentumu var ama..." cümlesini bununla kurar). 50 nötr.
def _momentum_lean(snap_tf) -> str:
    rsi = getattr(snap_tf, "rsi", None)
    macd = getattr(snap_tf, "macd", None)
    stack = getattr(snap_tf, "ema_stack", None)
    votes = 0
    if rsi is not None:
        votes += 1 if rsi >= 55 else (-1 if rsi <= 45 else 0)
    if macd is not None:
        votes += 1 if macd > 0 else (-1 if macd < 0 else 0)
    if stack == "bullish":
        votes += 1
    elif stack == "bearish":
        votes -= 1
    return "bullish" if votes > 0 else ("bearish" if votes < 0 else "neutral")


# ── location evidence → human Turkish phrase (deterministic; no LLM needed) ──
_FIB_ZONE_TR = {
    "near_support": "fiyat Fibonacci desteğine yakın",
    "near_resistance": "fiyat Fibonacci direncine yakın",
    "breakout": "fiyat direnci yukarı kırmış",
    "breakdown": "fiyat desteği aşağı kırmış",
    "mid_range": "fiyat orta bölgede",
}
_PATTERN_TR = {
    "uptrend_structure": "yükseliş yapısı",
    "downtrend_structure": "düşüş yapısı",
    "ranging": "yatay seyir",
}
_REV_TR = {"BULLISH": "yukarı dönüş sinyali", "BEARISH": "aşağı dönüş sinyali"}
_MOM_TR = {"bearish": "düşüş", "bullish": "yükseliş", "neutral": "nötr"}


def _humanize_location(evidence: list[str]) -> str:
    """fib_zone / confluence / pattern / reversal kanıtını düz Türkçe öbeğe çevirir."""
    parts: list[str] = []
    for e in evidence:
        if e.startswith("fib_zone="):
            z = e.split("=", 1)[1]
            if z in _FIB_ZONE_TR:
                parts.append(_FIB_ZONE_TR[z])
        elif e.startswith("confluence:"):
            m = re.match(r"confluence:(support|resistance)@([\d.]+)", e)
            if m:
                kind = "destek" if m.group(1) == "support" else "direnç"
                bits: list[str] = []
                cm = re.search(r"\[(.*?)\]", e)
                if cm:
                    if "swing" in cm.group(1):
                        bits.append("swing")
                    fib = re.search(r"fib_([\d.]+)%", cm.group(1))
                    if fib:
                        bits.append(f"Fib %{fib.group(1)}")
                comp = f" ({' + '.join(bits)})" if bits else ""
                parts.append(f"~{float(m.group(2)):,.0f} seviyesinde güçlü {kind}{comp}")
        elif e.startswith("pattern="):
            p = e.split("=", 1)[1]
            if p in _PATTERN_TR:
                parts.append(_PATTERN_TR[p])
        elif e.startswith("reversal_bias="):
            b = e.split("=", 1)[1].split(" ")[0]
            if b in _REV_TR:
                parts.append(_REV_TR[b])
    return ", ".join(parts)


def _humanize_gate(g: dict) -> str:
    """Bir gate hücresini tek insan cümlesine çevirir (fallback + LLM girdisi)."""
    sym, tf = g["symbol"], g["timeframe"]
    mom = _MOM_TR.get(g["momentum_lean"], g["momentum_lean"])
    loc = _humanize_location(g["location_evidence"]) or "fiyat konumu uygun değil"
    gate = float(g["location_gate"])
    pct = round(abs(1.0 - gate) * 100)
    if g["effect"] == "penalty":
        if g["momentum_lean"] == "bearish":
            return (
                f"{sym} {tf}: Düşüş momentumu var ama {loc} — desteğe doğru short "
                f"açmak için kötü konum; güven %{pct} kısıldı (×{gate:.2f})."
            )
        if g["momentum_lean"] == "bullish":
            return (
                f"{sym} {tf}: Yükseliş momentumu var ama {loc} — dirence doğru long "
                f"açmak için kötü konum; güven %{pct} kısıldı (×{gate:.2f})."
            )
        return (
            f"{sym} {tf}: Momentum nötr ve {loc} ile çelişiyor — temkinli; "
            f"güven %{pct} kısıldı (×{gate:.2f})."
        )
    return (
        f"{sym} {tf}: {mom.capitalize()} momentumu konumla teyitli ({loc}); "
        f"güven %{pct} arttı (×{gate:.2f})."
    )


def _technical_gate_summary(snap: MarketSnapshot) -> list[dict]:
    """Per-(symbol, TF) top-down location gate that meaningfully reshaped conviction.

    EVIDENCE only — facts the LLM can NARRATE ("bearish momentum but price sitting on
    support → don't short into support"). Only cells where the gate actually moved
    conviction (|×−1| ≥ 0.05) are included, ranked by impact, capped. The gate already
    shaped `direction_score`/bias upstream; nothing here writes back to the decision."""
    by_tf = snap.technicals_by_tf or {}
    rows: list[dict] = []
    for sym, cells in by_tf.items():
        for tf, t in (cells or {}).items():
            gate = getattr(t, "location_gate", None)
            if gate is None or abs(gate - 1.0) < 0.05:
                continue
            mom = _momentum_lean(t)
            gated_bias = (
                "bullish" if (t.direction_score or 50) > 55
                else ("bearish" if (t.direction_score or 50) < 45 else "neutral")
            )
            rows.append(
                {
                    "symbol": sym,
                    "timeframe": tf,
                    "momentum_lean": mom,           # gate ÖNCESİ ham yön
                    "gated_bias": gated_bias,        # gate SONRASI yön
                    "direction_score": t.direction_score,
                    "location_gate": gate,           # <1 ceza, >1 teyit
                    "effect": "penalty" if gate < 1.0 else "confirm",
                    "location_evidence": list(getattr(t, "location_evidence", []) or []),
                }
            )
    rows.sort(key=lambda r: abs(r["location_gate"] - 1.0), reverse=True)
    # YALNIZCA ham faktlar döner (momentum_lean, gated_bias, direction_score,
    # location_gate, location_evidence). LLM bu verilerle SORULAN soruya kendi
    # cevabını üretir — hazır cümle gömülmez. İnsan cümlesi (_humanize_gate) sadece
    # LLM kapalı fallback'te kullanılır.
    return rows[:6]


def _matrix_summary(view: dict) -> dict:
    cells = view.get("cells") or []
    top = sorted(cells, key=lambda c: -abs(float(c.get("score", 50)) - 50))[:TOP_CELL_COUNT]
    diffs = [
        {
            "symbol": c["symbol"],
            "timeframe": c["timeframe"],
            "candidate": c["candidate_action"],
            "final": c["action"],
            "blocked_by": list(c.get("blocked_by") or []),
            "reason": c.get("reason", ""),
        }
        for c in cells
        if c.get("candidate_action") != c.get("action")
    ]
    paper_actions = [
        {"symbol": c["symbol"], "timeframe": c["timeframe"], "paper_action": c["paper_action"]}
        for c in cells
        if c.get("paper_action") not in (None, "none")
    ]
    blocked_reasons = sorted(
        {b for c in cells for b in (c.get("blocked_by") or [])}
    )
    return {
        "suspended": bool(view.get("suspended")),
        "regime": view.get("regime"),
        "risk_gate": view.get("risk_gate"),
        "dqs_status": view.get("dqs_status"),
        "symbols": view.get("symbols"),
        "timeframes": view.get("timeframes"),
        "top_cells": [
            {
                "symbol": c["symbol"],
                "timeframe": c["timeframe"],
                "candidate": c["candidate_action"],
                "final": c["action"],
                "score": c["score"],
                "direction": c["direction"],
                "status": c["status"],
                "blocked_by": list(c.get("blocked_by") or []),
            }
            for c in top
        ],
        "candidate_vs_final_diffs": diffs,
        "paper_actions": paper_actions,
        "blocked_by_reasons": blocked_reasons,
    }


def build_compact_context() -> dict:
    snap = get_cached_snapshot()
    ps = paper_state.load()
    matrix_symbols = asset_registry.trade_symbols()
    risk_in = _risk_input(ps, snap)
    regime, risk, decisions = decide_matrix(
        matrix_symbols, snap, risk_in, open_positions=ps.open_positions
    )
    view = matrix_view(regime, risk, decisions, snap, matrix_symbols)

    halt_state = halt_store.load()
    active_halts = [
        {"type": e.type, "level": e.level, "reason": e.reason}
        for e in halt_store.active_halts(halt_state)
    ]

    corr_entries = correlation.matrix(
        sorted({*matrix_symbols, *(p.symbol for p in ps.open_positions)})
    )
    clusters = correlation.open_clusters(ps.open_positions, ps.equity_usd, corr_entries)

    mistakes = mistake_memory.summary()
    flagged = [
        {"fingerprint": m.fingerprint, "trades": m.trades, "win_rate": m.win_rate}
        for m in mistakes
    ][:5]

    # "unknown" = hiç çağrılmamış sağlayıcı (ör. mock, calls=0) — SORUN DEĞİL,
    # listelenmez. Yalnızca gerçek hata/degraded/stale durumları sorun sayılır.
    provider_issues = {
        name: meta
        for name, meta in (snap.provider_status or {}).items()
        if (meta or {}).get("status") not in (None, "ok", "OK", "unknown", "UNKNOWN")
    }

    return {
        "snapshot_id": snap.snapshot_id,
        "generated_at": snap.generated_at.isoformat(),
        "provenance": data_provenance(snap),
        "dqs": {
            "score": snap.quality.score,
            "status": snap.quality.status,
            "fallback_used": snap.quality.fallback_used,
            "notes": list(snap.quality.notes)[:5],
        },
        "provider_issues": provider_issues,
        "warnings": list(snap.warnings)[:6],
        "matrix": _matrix_summary(view),
        "technical_gate": _technical_gate_summary(snap),
        "deep_data": _deep_data_summary(view, snap),
        "halt": {"active": bool(active_halts), "events": active_halts},
        "correlation_clusters": clusters,
        "paper": {
            "equity_usd": round(ps.equity_usd, 2),
            "daily_pnl_usd": round(ps.daily_pnl_usd, 2),
            "realized_pnl_usd": round(ps.realized_pnl_usd, 2),
            "open_positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "timeframe": getattr(p, "timeframe", "1d"),
                    "size_usd": round(p.size_usd, 2),
                }
                for p in ps.open_positions
            ],
            "recent_trade_count": len(ps.recent_trades),
        },
        "learning": {"mistake_fingerprints": flagged},
        "news": [h.title for h in snap.headlines[:3]],
        "catalysts": [
            {"title": c.title, "importance": c.importance} for c in snap.catalysts[:3]
        ],
    }


# Digest'e GİRMEYEN volatil alanlar — snapshot_id her 30sn değişir; cache
# state aynı kaldıkça vurabilsin diye içerik bazlı anahtar kullanılır.
_VOLATILE_KEYS = ("snapshot_id", "generated_at")


def context_digest(ctx: dict) -> str:
    stable = {k: v for k, v in ctx.items() if k not in _VOLATILE_KEYS}
    raw = json.dumps(stable, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def context_for_prompt(ctx: dict) -> str:
    """Prompt'a gömülecek JSON (kompakt, deterministik sıralı)."""
    return json.dumps(ctx, sort_keys=True, ensure_ascii=False, default=str)


def no_actionable_decision(ctx: dict) -> bool:
    """DQS BLOCKED veya kısıtlayıcı risk gate → 'no actionable decision' modu."""
    return ctx["dqs"]["status"] == "BLOCKED" or bool(ctx["matrix"]["suspended"])


__all__ = [
    "build_compact_context",
    "context_digest",
    "context_for_prompt",
    "no_actionable_decision",
]
