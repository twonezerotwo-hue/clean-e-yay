"""Giriş motoru terfisi — NEW (entry_quality_v2) = PRIMARY, LEGACY = SHADOW + TEKNİK FALLBACK.

Kararın yönünü (konsensüs) ve girişin zamanlamasını (giriş kalitesi + dönüş riski) ayrı
eksenler olarak tutar; bu modül ikinci eksenin karar akışındaki KAPISINI ve karşılaştırma
telemetrisini sağlar. ``packages/decision/engine.py`` orkestrasyonu yapar; burası saf
yardımcıdır (``TradeDecision`` tipini import etmez → döngüsel bağımlılık yok).

    mode = off     → hiçbir şey hesaplanmaz; karar bayt-aynı (rollback: tek satır).
    mode = shadow  → LEGACY uygulanır; NEW yalnız hesaplanıp yan yana yazılır.
    mode = active  → NEW uygulanır (LONG / SHORT / WAIT üçü de GEÇERLİ karardır);
                     LEGACY aynı turda gölge olarak karşılaştırılır.

TEKNİK HATA ≠ WAIT. Yeni motor sağlıklı biçimde WAIT derse bu bilinçli karardır; legacy'nin
LONG/SHORT'u ASLA zorla uygulanmaz. Legacy'ye yalnız şunlarda düşülür: istisna, NaN/inf,
bozuk karar/rapor, zorunlu bağlamın eksikliği, geçersiz eylem, gecikme bütçesi aşımı, yeni
karar nesnesinin üretilememesi. Düşüş RiskGate'i atlamaz: legacy zincir de aynı çekirdektir
(RiskGate İLK sırada), sonra aynı session/conflict kapıları ve ``attempt_open`` çalışır.
"""
from __future__ import annotations

import logging
import math
from time import monotonic, perf_counter

from packages.scoring import entry_quality

log = logging.getLogger(__name__)

OPEN_ACTIONS = ("open_long", "open_short")
VALID_ACTIONS = (*OPEN_ACTIONS, "hold", "blocked")

ENGINE_NEW = "new"                    # active, teknik sorun yok → yeni motor uygulandı
ENGINE_FALLBACK = "legacy_fallback"   # active, yeni motor teknik olarak başarısız → legacy
ENGINE_LEGACY = "legacy"              # shadow → legacy uygulanır, yeni yalnız gözlenir

VETO_TAGS = {
    "entry_quality": "entry_quality_v2:entry_quality",
    "reversal_risk": "entry_quality_v2:reversal_risk",
    "reduce": "entry_quality_v2:reduce",
}

# --- süreç ömrü sayaçları (ucuz; "fallback normalde 0" izlemesi için) ---------------------
_STATS: dict = {"fallback_total": 0, "fallback_reasons": {}}
_LOG_EVERY_S = 600.0
_LAST_LOG: dict[str, float] = {}


def stats() -> dict:
    return {
        "fallback_total": int(_STATS["fallback_total"]),
        "fallback_reasons": dict(_STATS["fallback_reasons"]),
    }


def reset_stats() -> None:
    _STATS["fallback_total"] = 0
    _STATS["fallback_reasons"] = {}
    _LAST_LOG.clear()


def reason_class(reason: str | None) -> str:
    """``exception:ValueError`` → ``exception`` (sayaç/özet kardinalitesini sınırlar)."""
    return (reason or "unknown").split(":", 1)[0]


def count_fallback(reason: str, symbol: str, timeframe: str) -> None:
    """Gerçek (active) fallback'i say ve log'a seyrek yaz — fallback sistemik olsa bile
    tick başına 50 satır spam yok: sebep sınıfı başına en çok 10 dakikada bir WARNING."""
    cls = reason_class(reason)
    _STATS["fallback_total"] += 1
    _STATS["fallback_reasons"][cls] = _STATS["fallback_reasons"].get(cls, 0) + 1
    now = monotonic()
    if now - _LAST_LOG.get(cls, -_LOG_EVERY_S) >= _LOG_EVERY_S:
        _LAST_LOG[cls] = now
        log.warning(
            "entry_quality_v2 teknik fallback → legacy karar zinciri: %s %s sebep=%s "
            "(toplam=%d; bu sınıf için sonraki uyarı en erken %d dk sonra)",
            symbol, timeframe, reason, _STATS["fallback_total"], int(_LOG_EVERY_S // 60),
        )


def bucket(action: str | None) -> str | None:
    """Eylem → LONG / SHORT / WAIT kovası (hold + blocked = WAIT)."""
    if action is None:
        return None
    if action == "open_long":
        return "long"
    if action == "open_short":
        return "short"
    return "wait"


# --- kapı ----------------------------------------------------------------------------------

def gate(snap: object, symbol: str, timeframe: str, action: str, mode: str) -> dict:
    """Açık adayın giriş kalitesi + dönüş riski raporu. ASLA raise etmez.

    Başarı → ``assess`` raporu (+ ``applied_engine``). Teknik başarısızlık → kısıt YOK,
    ``fallback_reason`` dolu; çağıran karar zincirini legacy olarak sürdürür."""
    side = "long" if action == "open_long" else "short"
    cfg = None
    rep: dict = {}
    problem: str | None = None
    t0 = perf_counter()
    try:
        cfg = entry_quality.config()
        ctx = ((getattr(snap, "entry_contexts", None) or {}).get(symbol) or {}).get(timeframe)
        problem = entry_quality.context_problem(ctx)
        if problem is None:
            rep = entry_quality.assess(side, ctx, cfg)
            problem = entry_quality.report_problem(rep)
        if problem is None and (perf_counter() - t0) * 1000.0 > cfg.fallback_max_latency_ms:
            problem = "timeout"
    except Exception as exc:  # yeni motor ASLA kararı düşürmez → teknik fallback
        problem = f"exception:{type(exc).__name__}"
    gate_ms = round((perf_counter() - t0) * 1000.0, 3)

    if problem is not None:
        if mode == "active":
            count_fallback(problem, symbol, timeframe)
        return {
            "mode": mode, "side": side, "verdict": None, "entry_quality": None,
            "reversal_risk": None, "size_factor": None, "reasons": [], "events": [],
            "applied": False,
            "applied_engine": ENGINE_FALLBACK if mode == "active" else ENGINE_LEGACY,
            "fallback_reason": problem, "gate_ms": gate_ms,
        }
    rep["mode"] = mode
    rep["applied"] = mode == "active"
    rep["applied_engine"] = ENGINE_NEW if mode == "active" else ENGINE_LEGACY
    rep["fallback_reason"] = None
    rep["gate_ms"] = gate_ms
    return rep


def wait_tags(rep: dict) -> list[str]:
    """``wait`` kararının ``blocked_by`` etiketleri (sebep sırası korunur, tekrar yok)."""
    tags = [
        "reversal_risk" if r.startswith("reversal_risk") else "entry_quality"
        for r in rep.get("reasons") or []
        if r.startswith(("reversal_risk", "entry_quality"))
    ]
    return [f"entry_quality_v2:{t}" for t in dict.fromkeys(tags)]


# --- yeni karar nesnesinin teknik doğrulaması ----------------------------------------------

def _finite(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def decision_problem(d: object) -> str | None:
    """Yeni motorun ürettiği karar nesnesi teknik olarak geçersizse sebep (aksi None).

    Geçerli LONG / SHORT / WAIT için None döner — WAIT hata değildir. Ayrıca yeni motorun
    değişmezi kontrol edilir: eylem ya aday yön ya da hold/blocked'tır (ZIT YÖN yok)."""
    action = getattr(d, "action", None)
    if action not in VALID_ACTIONS:
        return "invalid_action"
    for attr in ("size_multiplier", "confidence"):
        if not _finite(getattr(d, attr, None)):
            return "non_finite_decision"
    if d.size_multiplier < 0:
        return "invalid_size"
    cand = getattr(d, "candidate_action", None)
    if action in OPEN_ACTIONS and action != cand:
        return "side_flip"
    rep = getattr(d, "entry_quality_report", None) or {}
    sf = rep.get("size_factor")
    if sf is not None and (not _finite(sf) or sf > 1.0):
        return "invalid_size_factor"
    return None


# --- telemetri -----------------------------------------------------------------------------

_EMPTY_VIEW = {"direction": None, "action": None, "score": None}


def view(d: object, action: str | None = None) -> dict:
    """Bir motorun kararının özeti (yön / eylem / skor). ``action`` verilirse eylemi ezer
    (shadow'daki hipotetik yeni eylem için)."""
    cons = getattr(d, "consensus", None)
    return {
        "direction": getattr(cons, "direction", None),
        "action": action if action is not None else getattr(d, "action", None),
        "score": getattr(cons, "score", None),
    }


def annotate(
    decision: object,
    *,
    mode: str,
    applied_engine: str,
    legacy: dict | None,
    new: dict | None,
    fallback_reason: str | None = None,
) -> dict:
    """Karar raporuna eski/yeni yan yana alanları yazar (yerinde) ve raporu döndürür.

    ``legacy`` / ``new``: ``view()`` çıktısı (motor karar üretmediyse None → alanlar None).
    Yön ve skor iki motorda AYNIDIR (yön katmanı değişmez; yeni motor zamanlama ekseni
    ekler); ``agreement`` eylemlerin eşitliğidir."""
    rep = decision.entry_quality_report
    if not isinstance(rep, dict):
        rep = {}
    rep.setdefault("mode", mode)
    rep["applied_engine"] = applied_engine
    rep["applied"] = applied_engine == ENGINE_NEW
    rep["fallback_reason"] = fallback_reason
    lv = legacy or _EMPTY_VIEW
    nv = new or _EMPTY_VIEW
    for key in ("direction", "action", "score"):
        rep[f"legacy_{key}"] = lv[key]
        rep[f"new_{key}"] = nv[key]
    rep["agreement"] = (
        None if lv["action"] is None or nv["action"] is None else lv["action"] == nv["action"]
    )
    decision.entry_quality_report = rep
    return rep


def shadow_new_action(applied_action: str, rep: dict) -> str:
    """Shadow'da yeni motorun HİPOTETİK eylemi: giriş adayına ``wait`` derse hold."""
    if applied_action in OPEN_ACTIONS and rep.get("verdict") == "wait":
        return "hold"
    return applied_action


def summarize(cells: list[dict], mode: str) -> dict:
    """Matrix hücrelerinden tek-tur motor karşılaştırma özeti (izleme için).

    ``applied_*`` üretimde uygulanan eylemler; ``legacy`` gölge motorun eylemleri; ``new``
    yeni motorun kendi eylemleri (fallback hücrelerinde yeni motor karar üretmedi →
    ``new_unavailable``)."""
    new = {"long": 0, "short": 0, "wait": 0}
    leg = {"long": 0, "short": 0, "wait": 0}
    evaluated = disagree = eq_veto = rr_veto = reduced = fb = new_unavailable = 0
    reasons: dict[str, int] = {}
    ms: list[float] = []
    for c in cells:
        rep = c.get("entry_quality") or {}
        action = c.get("action")
        failed = bool(rep.get("fallback_reason"))
        l_act = rep.get("legacy_action") or action
        n_act = None if failed else (rep.get("new_action") or action)
        leg[bucket(l_act) or "wait"] += 1
        if n_act is None:
            new_unavailable += 1
        else:
            new[bucket(n_act) or "wait"] += 1
        if not rep:
            continue
        if failed:
            fb += 1
            cls = reason_class(rep.get("fallback_reason"))
            reasons[cls] = reasons.get(cls, 0) + 1
        elif rep.get("agreement") is not None:
            evaluated += 1
            disagree += 0 if rep["agreement"] else 1
        blocked = c.get("blocked_by") or []
        eq_veto += VETO_TAGS["entry_quality"] in blocked
        rr_veto += VETO_TAGS["reversal_risk"] in blocked
        reduced += VETO_TAGS["reduce"] in blocked
        if isinstance(rep.get("gate_ms"), (int, float)):
            ms.append(float(rep["gate_ms"]))
    return {
        "mode": mode,
        "primary": "new" if mode == "active" else "legacy",
        "shadow": "legacy" if mode == "active" else "new",
        "cells": len(cells),
        "evaluated": evaluated,
        "new": new,
        "legacy": leg,
        "new_unavailable": new_unavailable,
        "disagreements": disagree,
        "disagreement_pct": round(100.0 * disagree / evaluated, 2) if evaluated else 0.0,
        "entry_quality_veto": int(eq_veto),
        "reversal_risk_veto": int(rr_veto),
        "reduced": int(reduced),
        "fallback": {"count": fb, "reasons": reasons, **stats()},
        "gate_ms": {
            "avg": round(sum(ms) / len(ms), 3) if ms else 0.0,
            "max": round(max(ms), 3) if ms else 0.0,
        },
    }


__all__ = [
    "ENGINE_FALLBACK",
    "ENGINE_LEGACY",
    "ENGINE_NEW",
    "OPEN_ACTIONS",
    "VALID_ACTIONS",
    "annotate",
    "bucket",
    "count_fallback",
    "decision_problem",
    "gate",
    "reason_class",
    "reset_stats",
    "shadow_new_action",
    "stats",
    "summarize",
    "view",
    "wait_tags",
]
