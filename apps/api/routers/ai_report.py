"""GET /api/v1/ai-report/current

v2.6 — persona bölümleri (LLM veya deterministik fallback) + timeframe
özeti eklendi. LLM karar VERMEZ: rapor yalnızca mevcut state'i anlatır;
verdict/narrative deterministik motorlardan gelir.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.agent.llm import context as llm_context
from packages.agent.llm import report as llm_report
from packages.agent.narrative import build_narrative
from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.data.provenance import data_provenance, decision_disclaimer
from packages.regime.classifier import classify

router = APIRouter(tags=["ai"])


def _timeframe_summary(ctx: dict) -> dict:
    """DecisionMatrix'in rapor özeti — 15m/1h/4h/1d/1w farkları,
    candidate vs final, blocked_by, paper_action (frontend hesap yapmaz)."""
    m = ctx["matrix"]
    lines = [
        f"{c['symbol']} {c['timeframe']}: {c['direction']} {c['score']:.0f} → "
        f"final {c['final']}" + (f" [{', '.join(c['blocked_by'])}]" if c["blocked_by"] else "")
        for c in m["top_cells"]
    ]
    return {
        "suspended": m["suspended"],
        "lines": lines,
        "candidate_vs_final_diffs": m["candidate_vs_final_diffs"],
        "blocked_by_reasons": m["blocked_by_reasons"],
        "paper_actions": m["paper_actions"],
    }


@router.get("/ai-report/current")
def get_ai_report_current() -> dict:
    snap = get_cached_snapshot()
    regime = classify(snap)
    cons_list = [build_consensus(s, snap, regime) for s in DEFAULT_SYMBOLS[:6]]
    verdict, narrative, key_signals = build_narrative(cons_list, regime)
    prov = data_provenance(snap)
    disclaimer = decision_disclaimer(snap)
    if disclaimer is not None:
        narrative = f"{disclaimer}\n\n{narrative}"
        key_signals = [disclaimer, *key_signals]

    # v2.6 — persona katmanı (narrative-only; decision path'e yazmaz).
    ctx = llm_context.build_compact_context()
    no_action = llm_context.no_actionable_decision(ctx)
    if no_action:
        verdict = "no_trade"
        narrative = (
            "NO ACTIONABLE DECISION — DQS BLOCKED veya risk gate kısıtlayıcı; "
            "rapor yalnızca durumu açıklar, aksiyon önermez.\n\n" + narrative
        )
    sections, llm_meta = llm_report.build_persona_sections(ctx)

    return {
        "meta": {
            "snapshot_id": snap.snapshot_id,
            "generated_at": snap.generated_at.isoformat(),
            "dqs_score": snap.quality.score,
            "fallback_used": snap.quality.fallback_used,
        },
        "mode": prov,
        "verdict": verdict,
        "narrative": narrative,
        "key_signals": key_signals,
        "no_actionable_decision": no_action,
        "timeframe_summary": _timeframe_summary(ctx),
        "personas": sections,
        "llm": llm_meta,
        "token_usage": {
            "input": 0,
            "output": int(llm_meta.get("tokens_used") or 0),
            "cached": bool(llm_meta.get("cached")),
        },
    }
