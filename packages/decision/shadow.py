"""Step 9 — controlled activation (observation mode).

The NEW additive agent pipeline (`agent_pipeline`) is run alongside the live
`decide_matrix` engine and its decision is recorded next to the live decision for
comparison. This is OBSERVATION ONLY: nothing here opens, sizes, or queues a trade,
and `observe()` never receives or mutates paper state.

The single invariant that governs activation is `affects_paper(cfg)` —
`enabled and affect_decision`. In Phase A (this module) it is wired nowhere that
mutates paper; the worker only calls `observe()` + `record()`. Phase B will add an
`activate()` path that, when `affect_decision` is true, routes shadow entries to
the manual_ready queue ONLY (never an auto-open) — RiskGate stays the final
authority, upper-TF only scales down, and `manual_ready_only` is honoured.

Storage mirrors `learning/decision_log.py`: append-only JSONL, best-effort writes
that never raise, corrupt lines skipped on read, `SHADOW_LOG_PATH` env override.

PAPER_SAFE / NO_EXECUTION: only records a comparison; never opens/sizes/decides.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.data.registry.loader import load_thresholds
from packages.decision import agent_pipeline

DEFAULT_PATH = "data/runtime/shadow_decisions.jsonl"
DEFAULT_MAX_READ = 200
EXECUTION_MODE = "PAPER"  # NO_EXECUTION contract — observation is paper-only.

# Live engine actions that represent a NEW entry intent.
_LIVE_ENTRY_ACTIONS = ("open_long", "open_short")
# Shadow (AgentDecision) actions that represent a NEW entry intent.
_SHADOW_ENTRY_ACTIONS = ("SCOUT_ALLOWED", "CONFIRMATION_REQUIRED")


@dataclass(frozen=True)
class ShadowConfig:
    """`shadow:` config block — conservative defaults (disabled / observe-only)."""

    enabled: bool = False
    affect_decision: bool = False
    manual_ready_only: bool = True


def load_config() -> ShadowConfig:
    s = load_thresholds().get("shadow", {}) or {}
    return ShadowConfig(
        enabled=bool(s.get("enabled", False)),
        affect_decision=bool(s.get("affect_decision", False)),
        manual_ready_only=bool(s.get("manual_ready_only", True)),
    )


def affects_paper(cfg: ShadowConfig) -> bool:
    """The ONE gate for activation: shadow may touch paper only when BOTH flags set.

    Phase A keeps `affect_decision` false, so this is always false and the worker
    runs observe-only. Phase B's `activate()` will guard on exactly this.
    """
    return cfg.enabled and cfg.affect_decision


def _path() -> Path:
    return Path(os.environ.get("SHADOW_LOG_PATH", DEFAULT_PATH))


def _live_direction(action: str) -> str | None:
    if action == "open_long":
        return "long"
    if action == "open_short":
        return "short"
    return None


def _shadow_direction(view: Any) -> str | None:
    """Entry direction from the composed consensus (>50 bullish, <50 bearish)."""
    score = getattr(getattr(view, "consensus", None), "direction_score", None)
    if score is None:
        return None
    if score > 50:
        return "long"
    if score < 50:
        return "short"
    return None


def _live_for_symbol(symbol: str, live_decisions: Sequence[Any]) -> dict:
    """Collapse the live (symbol, timeframe) decisions into one per-symbol intent.

    A symbol "wants an entry" if ANY of its cells is an actionable open_*; the
    representative entry is the actionable one with the highest confidence.
    """
    cells = [d for d in live_decisions if getattr(d, "symbol", None) == symbol]
    entries = [
        d
        for d in cells
        if getattr(d, "action", None) in _LIVE_ENTRY_ACTIONS
        and bool(getattr(d, "actionable", False))
    ]
    top = max(entries, key=lambda d: float(getattr(d, "confidence", 0.0) or 0.0), default=None)
    return {
        "wants_entry": bool(entries),
        "action": getattr(top, "action", None) if top is not None else None,
        "direction": _live_direction(getattr(top, "action", "")) if top is not None else None,
        "timeframe": getattr(top, "timeframe", None) if top is not None else None,
        "size_multiplier": float(getattr(top, "size_multiplier", 0.0) or 0.0) if top is not None else 0.0,
        "confidence": float(getattr(top, "confidence", 0.0) or 0.0) if top is not None else 0.0,
        "entry_cells": len(entries),
        "evaluated_cells": len(cells),
    }


def _shadow_for_symbol(view: Any) -> dict:
    decision = getattr(view, "decision", None)
    action = getattr(decision, "action", None)
    return {
        "wants_entry": action in _SHADOW_ENTRY_ACTIONS,
        "action": action,
        "entry_timeframe": getattr(decision, "entry_timeframe", None),
        "direction": _shadow_direction(view),
        "size_multiplier": float(getattr(decision, "size_multiplier", 0.0) or 0.0),
        "stance": getattr(getattr(view, "agent", None), "stance", None),
    }


def _agreement(live: dict, shadow: dict) -> str:
    """Coarse, deterministic agreement label between live and shadow intent."""
    lw, sw = live["wants_entry"], shadow["wants_entry"]
    if not lw and not sw:
        return "AGREE_FLAT"
    if lw and sw:
        if live["direction"] and live["direction"] == shadow["direction"]:
            return "AGREE_ENTRY"
        return "DISAGREE_DIRECTION"
    return "LIVE_ONLY_ENTRY" if lw else "SHADOW_ONLY_ENTRY"


def build_comparison(
    *,
    snapshot_id: str | None,
    risk_action: str | None,
    live_decisions: Sequence[Any],
    shadow_views: Sequence[Any],
    cfg: ShadowConfig,
    calibration: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Pure comparison record: per-symbol live-vs-shadow intent + agreement summary.

    No I/O, no paper access. `affected_paper` is stamped from `affects_paper(cfg)`
    so the record always tells the truth about whether the shadow could have moved
    paper (false throughout Phase A). `calibration` is an opaque trust verdict
    (computed by the caller, which owns paper state) embedded for the watcher — it
    surfaces whether the consensus tf_weights are still PRIOR/untrusted, so the
    eventual decision to apply them is data-driven, never guessed.
    """
    now = now or datetime.now(UTC)
    rows: list[dict] = []
    counts: dict[str, int] = {
        "AGREE_ENTRY": 0,
        "AGREE_FLAT": 0,
        "DISAGREE_DIRECTION": 0,
        "LIVE_ONLY_ENTRY": 0,
        "SHADOW_ONLY_ENTRY": 0,
    }
    for view in shadow_views:
        symbol = getattr(view, "symbol", None)
        live = _live_for_symbol(symbol, live_decisions)
        shadow = _shadow_for_symbol(view)
        agreement = _agreement(live, shadow)
        counts[agreement] = counts.get(agreement, 0) + 1
        rows.append(
            {"symbol": symbol, "live": live, "shadow": shadow, "agreement": agreement}
        )

    recorded_at = now.isoformat()
    return {
        # Deterministic id (replay-friendly): same snapshot + tick → same record_id.
        "record_id": f"{snapshot_id}:{recorded_at}",
        "recorded_at": recorded_at,
        "snapshot_id": snapshot_id,
        "risk_action": risk_action,
        "affect_decision": cfg.affect_decision,
        # Phase A invariant: observation never moves paper. Stamped from the one gate.
        "affected_paper": affects_paper(cfg),
        # tf_weights trust verdict (PRIOR/untrusted until per-TF calibration validates).
        "calibration": calibration or {},
        "symbols": rows,
        "summary": counts,
        # Safety contract stamped on every record (audit/replay evidence).
        "execution_mode": EXECUTION_MODE,
        "paper_safe": True,
        "no_execution": True,
    }


def calibration_summary(report: dict | None) -> dict:
    """Trim a tf_calibration report to a compact, watcher-facing trust verdict.

    Pure dict→dict (no learning/paper import). Keeps each shadow record lean while
    still answering "are the consensus tf_weights trusted yet, and how close?".
    """
    if not report:
        return {}
    return {
        "tf_weights_trusted": bool(report.get("tf_weights_trusted", False)),
        "calibrated_timeframes": list(report.get("calibrated_timeframes", []) or []),
        "min_trades_per_tf": report.get("min_trades_per_tf"),
        "per_timeframe": [
            {
                "timeframe": c.get("timeframe"),
                "strategy": c.get("strategy"),
                "trades": c.get("trades"),
                "win_rate": c.get("win_rate"),
                "trust": c.get("trust"),
            }
            for c in (report.get("per_timeframe") or [])
        ],
    }


def observe(
    symbols: list[str],
    *,
    snapshot_id: str | None,
    risk_action: str | None,
    live_decisions: Sequence[Any],
    cfg: ShadowConfig | None = None,
    calibration: dict | None = None,
    build_views: Callable[..., Sequence[Any]] | None = None,
) -> dict:
    """Run the shadow pipeline and build the comparison record (no paper access).

    `build_views` is injectable for tests; in production it defaults to
    `agent_pipeline.build_agent_matrix` (cache-backed bars, read-only). This function
    NEVER opens, sizes, or queues a trade — it only composes the new pipeline's view
    and compares it to the live decisions. `calibration` is an opaque trust verdict
    supplied by the caller (which owns paper state); it is embedded, never recomputed
    here, so this module stays paper-free.
    """
    cfg = cfg or load_config()
    builder = build_views or agent_pipeline.build_agent_matrix
    shadow_views = builder(symbols, risk_action=risk_action)
    return build_comparison(
        snapshot_id=snapshot_id,
        risk_action=risk_action,
        live_decisions=live_decisions,
        shadow_views=shadow_views,
        cfg=cfg,
        calibration=calibration,
    )


_AGREEMENTS = (
    "AGREE_ENTRY",
    "AGREE_FLAT",
    "DISAGREE_DIRECTION",
    "LIVE_ONLY_ENTRY",
    "SHADOW_ONLY_ENTRY",
)


def comparison_viewmodel(record: dict | None) -> dict:
    """Flatten the latest shadow record into a render-only ViewModel (frontend does
    no math). Missing record → an explicit `available: false` empty shell so the
    panel can show "no shadow data yet" without inventing values."""
    if not record:
        return {
            "available": False,
            "recorded_at": None,
            "snapshot_id": None,
            "risk_action": None,
            "affect_decision": False,
            "affected_paper": False,
            "summary": {k.lower(): 0 for k in _AGREEMENTS},
            "calibration": {
                "tf_weights_trusted": False,
                "calibrated_timeframes": [],
                "min_trades_per_tf": None,
                "per_timeframe": [],
            },
            "rows": [],
        }
    summary_src = record.get("summary") or {}
    cal = record.get("calibration") or {}
    rows = []
    for s in record.get("symbols") or []:
        live = s.get("live") or {}
        shadow_ = s.get("shadow") or {}
        rows.append(
            {
                "symbol": s.get("symbol"),
                "agreement": s.get("agreement"),
                "live_wants_entry": bool(live.get("wants_entry")),
                "live_action": live.get("action"),
                "live_direction": live.get("direction"),
                "live_timeframe": live.get("timeframe"),
                "shadow_wants_entry": bool(shadow_.get("wants_entry")),
                "shadow_action": shadow_.get("action"),
                "shadow_direction": shadow_.get("direction"),
                "shadow_entry_timeframe": shadow_.get("entry_timeframe"),
                "shadow_stance": shadow_.get("stance"),
            }
        )
    return {
        "available": True,
        "recorded_at": record.get("recorded_at"),
        "snapshot_id": record.get("snapshot_id"),
        "risk_action": record.get("risk_action"),
        "affect_decision": bool(record.get("affect_decision")),
        "affected_paper": bool(record.get("affected_paper")),
        "summary": {k.lower(): int(summary_src.get(k, 0)) for k in _AGREEMENTS},
        "calibration": {
            "tf_weights_trusted": bool(cal.get("tf_weights_trusted", False)),
            "calibrated_timeframes": list(cal.get("calibrated_timeframes") or []),
            "min_trades_per_tf": cal.get("min_trades_per_tf"),
            "per_timeframe": list(cal.get("per_timeframe") or []),
        },
        "rows": rows,
    }


def latest_viewmodel() -> dict:
    """Read the most recent shadow record from disk → render-only ViewModel."""
    recent = read_recent(limit=1)
    return comparison_viewmodel(recent[-1] if recent else None)


def record(entry: dict) -> dict:
    """Append a shadow comparison record (best-effort; never raises)."""
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        # Observation ASLA tick'i kesmez — yazım başarısızsa sessizce geç.
        pass
    return entry


def read_recent(limit: int = DEFAULT_MAX_READ) -> list[dict]:
    """Son `limit` shadow kaydı (en yeni en sonda); bozuk satır atlanır."""
    p = _path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-max(1, limit):]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out
