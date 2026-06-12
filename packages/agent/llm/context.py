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

from packages.data.ingestion.pipeline import (
    DEFAULT_SYMBOLS,
    MarketSnapshot,
    get_cached_snapshot,
)
from packages.data.provenance import data_provenance
from packages.decision.engine import decide_matrix, matrix_view
from packages.learning import mistake_memory
from packages.paper import state as paper_state
from packages.risk import correlation
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

MATRIX_SYMBOLS = DEFAULT_SYMBOLS[:4]
TOP_CELL_COUNT = 8


def _risk_input(ps: paper_state.PaperState, snap: MarketSnapshot) -> RiskInput:
    return RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )


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
    risk_in = _risk_input(ps, snap)
    regime, risk, decisions = decide_matrix(
        MATRIX_SYMBOLS, snap, risk_in, open_positions=ps.open_positions
    )
    view = matrix_view(regime, risk, decisions, snap, MATRIX_SYMBOLS)

    halt_state = halt_store.load()
    active_halts = [
        {"type": e.type, "level": e.level, "reason": e.reason}
        for e in halt_store.active_halts(halt_state)
    ]

    corr_entries = correlation.matrix(
        sorted({*MATRIX_SYMBOLS, *(p.symbol for p in ps.open_positions)})
    )
    clusters = correlation.open_clusters(ps.open_positions, ps.equity_usd, corr_entries)

    mistakes = mistake_memory.summary()
    flagged = [
        {"fingerprint": m.fingerprint, "trades": m.trades, "win_rate": m.win_rate}
        for m in mistakes
    ][:5]

    provider_issues = {
        name: meta
        for name, meta in (snap.provider_status or {}).items()
        if (meta or {}).get("status") not in (None, "ok", "OK")
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
    "MATRIX_SYMBOLS",
    "build_compact_context",
    "context_digest",
    "context_for_prompt",
    "no_actionable_decision",
]
