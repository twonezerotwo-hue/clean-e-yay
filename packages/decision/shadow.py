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
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.data.providers import ohlcv
from packages.data.registry.loader import load_thresholds
from packages.decision import agent_pipeline, conflict_resolver
from packages.elliott import engine as elliott_engine
from packages.learning import historical_edge, tf_contribution
from packages.liquidity import sweep as liquidity_sweep_engine
from packages.mode import config as mode_config
from packages.mode import filter as mode_filter
from packages.mode import profile_selector
from packages.risk.trade_economics import compute_adaptive_targets, compute_fixed_targets
from packages.scoring import exhaustion as exhaustion_engine
from packages.setup import classifier as setup_classifier
from packages.volume import engine as volume_engine
from packages.zones import engine as zone_engine

_log = logging.getLogger(__name__)

# ConsensusSnapshot/per_timeframe key naming (m15..w1) → entry timeframe label.
_KEY_BY_TF = {"15m": "m15", "1h": "h1", "4h": "h4", "1d": "d1", "1w": "w1"}

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
        # Additive — historical_edge lookup anahtarı (bkz. _evidence_for_symbol).
        "fingerprint": getattr(top, "fingerprint", None) if top is not None else None,
    }


def _evidence_for_symbol(symbol: str | None, *, fingerprint: str | None, timeframe: str | None) -> dict:
    """Additive, read-only kanıt özeti: Elliott senaryosu + fuzzy historical edge.

    Bu fonksiyon `agreement`/`wants_entry` hesabını ETKİLEMEZ — yalnızca shadow
    kaydına ekstra gözlem alanı ekler. Her adım defensive: bar/veri yoksa veya
    bir hesap patlarsa boş dict döner, observe() ASLA bundan dolayı çökmez
    (mevcut "observation never breaks the tick" sözleşmesi, bkz. modül docstring).
    """
    if not symbol:
        return {}
    tf = timeframe or "1d"
    out: dict = {}
    try:
        bars = ohlcv.get_bars(symbol, tf) or []
        elliott = elliott_engine.analyze(bars, timeframe=tf)
        out["elliott"] = {
            "primary_scenario": elliott.primary_scenario,
            "confidence": elliott.confidence,
            "bias": elliott.bias,
        }
    except Exception:
        _log.warning("shadow evidence: elliott failed for %s/%s", symbol, tf, exc_info=True)
        out["elliott"] = {}
    try:
        if fingerprint:
            edge = historical_edge.compute_edge(fingerprint)
            out["historical_edge"] = {
                "sample_count": edge.sample_count,
                "win_rate": edge.win_rate,
                "edge_confidence": edge.edge_confidence,
            }
        else:
            out["historical_edge"] = {}
    except Exception:
        _log.warning("shadow evidence: historical_edge failed for %s", symbol, exc_info=True)
        out["historical_edge"] = {}
    return out


def _entry_tf_result(view: Any, entry_timeframe: str | None) -> Any | None:
    """view.agent.per_timeframe[key] için entry_timeframe karşılığı (yoksa None)."""
    key = _KEY_BY_TF.get(entry_timeframe or "")
    if key is None:
        return None
    per_tf = getattr(getattr(view, "agent", None), "per_timeframe", None) or {}
    return per_tf.get(key)


def _setup_and_conflict_for_symbol(
    view: Any,
    *,
    fingerprint: str | None,
    risk_action: str | None,
    dqs_status: str,
) -> dict:
    """Setup Classifier + Conflict Resolver — additive, gözlem amaçlı (spec v2.3 §19/§28).

    Sadece zaten hesaplanmış kanıtları (consensus, decision, economics, entry TF
    technical result, Elliott, historical edge) okur. Hiçbir karar zincirini
    etkilemez; bu fonksiyonun çıktısı sadece shadow kaydına eklenir. Her adım
    defensive — hesap patlarsa boş dict döner, observe() ASLA çökmez.
    """
    try:
        consensus = getattr(view, "consensus", None)
        decision = getattr(view, "decision", None)
        economics = getattr(view, "economics", None)
        entry_tf = getattr(decision, "entry_timeframe", None)
        entry_result = _entry_tf_result(view, entry_tf)

        chart_patterns = getattr(entry_result, "chart_pattern_analysis", None)
        reversal = getattr(entry_result, "reversal_signals", None)
        trend = getattr(entry_result, "trend_strength", None)

        symbol = getattr(view, "symbol", None)
        tf = entry_tf or "1d"
        bars = ohlcv.get_bars(symbol, tf) or [] if symbol else []
        elliott = elliott_engine.analyze(bars, timeframe=tf)

        # Faz 4 — additive: Faz 1/2 motorlarından (Volume/Liquidity-Sweep/
        # Exhaustion/Zone) kanıt üretip Setup Classifier'a besle.
        current_price = bars[-1].close if bars else None
        volume = volume_engine.analyze(bars, timeframe=tf)
        sweep = liquidity_sweep_engine.analyze(bars, timeframe=tf)
        exhaustion = exhaustion_engine.analyze(bars, timeframe=tf, volume=volume, sweep=sweep)
        zone = zone_engine.analyze(bars, timeframe=tf, current_price=current_price)

        setup_inputs = setup_classifier.SetupInputs(
            direction_score=getattr(consensus, "direction_score", None),
            alignment_status=getattr(consensus, "alignment_status", "CONFLICTED"),
            is_countertrend=bool(getattr(consensus, "is_countertrend", False)),
            entry_timeframe=entry_tf,
            volatility_regime=getattr(entry_result, "volatility_regime", "UNKNOWN"),
            trend_label=getattr(trend, "label", "UNKNOWN"),
            is_trending=bool(getattr(trend, "is_trending", False)),
            chart_pattern_names=tuple(
                p.name for p in (getattr(chart_patterns, "active_patterns", None) or [])
            ),
            reversal_bias=getattr(reversal, "bias", "NEUTRAL"),
            zone_location=zone.location if zone.validity != "unavailable" else None,
            elliott_scenario=elliott.primary_scenario,
            elliott_bias=elliott.bias,
            elliott_confidence=elliott.confidence,
            liquidity_sweep_bias=sweep.bias if sweep.validity != "unavailable" else "unknown",
            exhaustion_score=exhaustion.score if exhaustion.validity != "unavailable" else None,
            volume_state=volume.state if volume.validity != "unavailable" else None,
            volume_price_direction=volume.price_direction if volume.validity != "unavailable" else None,
        )
        setup_result = setup_classifier.classify(setup_inputs)

        edge_strong_negative = False
        if fingerprint:
            edge = historical_edge.compute_edge(fingerprint)
            edge_strong_negative = historical_edge.is_strong_negative(edge)

        # Faz 4 — additive: Trade Profile Selector + Agent Mode Filter.
        trade_profile = profile_selector.select_profile(setup_result.setup_type, entry_tf)
        mode_cfg = mode_config.load_config()
        mode_result = mode_filter.evaluate(
            setup_type=setup_result.setup_type,
            trade_profile=trade_profile,
            is_countertrend=bool(getattr(consensus, "is_countertrend", False)),
            cfg=mode_cfg,
        )

        conflict_inputs = conflict_resolver.ConflictInputs(
            dqs_status="BAD" if dqs_status == "BLOCKED" else dqs_status,
            risk_gate_action=risk_action or "HOLD",
            trigger_confirmed=getattr(decision, "action", None) == "SCOUT_ALLOWED",
            sl_tp_rr_valid=bool(getattr(economics, "allow", False)) if economics is not None else False,
            setup_type=setup_result.setup_type,
            historical_edge_strong_negative=edge_strong_negative,
            size_multiplier=float(getattr(decision, "size_multiplier", 0.0) or 0.0),
            alignment_status=getattr(consensus, "alignment_status", "CONFLICTED"),
            elliott_scenario=elliott.primary_scenario,
            elliott_confidence=elliott.confidence,
            mode_filter_passed=mode_result.passed,
            mode_filter_blocked_reason=mode_result.blocked_reason,
            trade_profile=trade_profile,
        )
        resolution = conflict_resolver.resolve(conflict_inputs)

        # Additive — fixed-% (what lifecycle.open_position ACTUALLY uses) vs
        # adaptive ATR/S-R targets (what the ticket card shows), side-by-side, for
        # this would-be entry. Observation only; never affects setup/conflict/
        # agreement. Needs a side + entry + ATR — skip (empty) if any are missing
        # rather than fabricate.
        target_comparison: dict = {}
        try:
            # setup_result.direction is "LONG"/"SHORT"/None (uppercase) —
            # compute_fixed_targets/compute_adaptive_targets take lowercase.
            side = (setup_result.direction or "").lower() or None
            key_levels = getattr(entry_result, "key_levels", None)
            atr = getattr(key_levels, "atr", None)
            if side in ("long", "short") and current_price and atr:
                fixed = compute_fixed_targets(
                    symbol or "", side, current_price,
                    predicted_confidence=getattr(decision, "confidence", None),
                )
                adaptive = compute_adaptive_targets(
                    side, current_price, atr,
                    support=getattr(key_levels, "support", None),
                    resistance=getattr(key_levels, "resistance", None),
                )
                target_comparison = {
                    "side": side,
                    "entry": round(current_price, 4),
                    "fixed": {"sl": fixed.sl, "tp": fixed.tp, "rr": fixed.rr, "sl_basis": fixed.sl_basis},
                    "adaptive": {
                        "sl": adaptive.sl, "tp": adaptive.tp, "rr": adaptive.rr,
                        "tp_basis": adaptive.tp_basis, "rr_floor_met": adaptive.rr_floor_met,
                    },
                }
        except Exception:
            _log.warning(
                "shadow target_comparison failed for %s", symbol, exc_info=True,
            )
            target_comparison = {}

        return {
            "setup_type": setup_result.setup_type,
            "setup_reason": setup_result.reason,
            "setup_direction": setup_result.direction,
            "trade_profile": trade_profile,
            "mode_filter_passed": mode_result.passed,
            "mode_filter_blocked_reason": mode_result.blocked_reason,
            "conflict_final_action": resolution.final_action,
            "conflict_blocked_by": list(resolution.blocked_by),
            "conflict_path": list(resolution.conflict_resolution_path),
            "target_comparison": target_comparison,
        }
    except Exception:
        _log.warning(
            "shadow setup_conflict failed for %s — bu tick'in Faz 9A retrospektif "
            "verisinde 'unmatched' olarak görünecek",
            getattr(view, "symbol", "?"),
            exc_info=True,
        )
        return {}


def evaluate_symbol(
    view: Any, *, fingerprint: str | None, risk_action: str | None, dqs_status: str
) -> dict:
    """Public giriş noktası — Setup Classifier + Conflict Resolver'ı tek bir sembol
    view'i için değerlendirir (Faz 7 — `conflict_resolver_activation.py` bunu kullanır).

    `build_comparison()`'ın her satır için zaten yaptığı hesabın aynısıdır; burada
    sadece dışarıdan çağrılabilir hale getirilmiştir. Read-only, paper'a dokunmaz.
    """
    return _setup_and_conflict_for_symbol(
        view, fingerprint=fingerprint, risk_action=risk_action, dqs_status=dqs_status
    )


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
    tf_weights: dict[str, float] | None = None,
    now: datetime | None = None,
    dqs_status: str = "OK",
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
    contributions: dict[str, dict[str, float]] = {}
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
        # Additive — agreement/wants_entry hesabını etkilemez (bkz. _evidence_for_symbol).
        evidence = _evidence_for_symbol(
            symbol, fingerprint=live.get("fingerprint"), timeframe=live.get("timeframe")
        )
        # Additive — Setup Classifier + Conflict Resolver (spec v2.3 §19/§28),
        # tamamen gözlem amaçlı; agreement/wants_entry hesabını etkilemez.
        setup_conflict = _setup_and_conflict_for_symbol(
            view, fingerprint=live.get("fingerprint"), risk_action=risk_action, dqs_status=dqs_status
        )
        rows.append(
            {
                "symbol": symbol,
                "live": live,
                "shadow": shadow,
                "agreement": agreement,
                "evidence": evidence,
                "setup_conflict": setup_conflict,
            }
        )
        # Per-TF contribution share — empty when nothing pushed (no faking).
        share = tf_contribution.compute_snapshot(view, tf_weights=tf_weights)
        if share and symbol is not None:
            contributions[symbol] = share

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
        # Per-TF score-contribution shares per symbol (sum=1.0 per symbol; empty when
        # no TF pushed). Closes the deferred contribution-attribution path: learning
        # correlates closed trades to this snapshot by (snapshot_id, symbol).
        "contributions": contributions,
        "tf_weights_applied": bool(tf_weights),
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
    tf_weights: dict[str, float] | None = None,
    build_views: Callable[..., Sequence[Any]] | None = None,
    dqs_status: str = "OK",
) -> dict:
    """Run the shadow pipeline and build the comparison record (no paper access).

    `build_views` is injectable for tests; in production it defaults to
    `agent_pipeline.build_agent_matrix` (cache-backed bars, read-only). This function
    NEVER opens, sizes, or queues a trade — it only composes the new pipeline's view
    and compares it to the live decisions. `calibration` is an opaque trust verdict
    supplied by the caller (which owns paper state); it is embedded, never recomputed
    here, so this module stays paper-free. `dqs_status` (OK/DEGRADED/BLOCKED) feeds
    the additive Conflict Resolver evidence only — never the agreement calculation.
    """
    cfg = cfg or load_config()
    builder = build_views or agent_pipeline.build_agent_matrix
    try:
        shadow_views = builder(symbols, risk_action=risk_action, tf_weights=tf_weights)
    except TypeError:
        # Builder stub may not accept tf_weights — strategy-agnostic fallback is fine.
        shadow_views = builder(symbols, risk_action=risk_action)
    return build_comparison(
        snapshot_id=snapshot_id,
        risk_action=risk_action,
        live_decisions=live_decisions,
        shadow_views=shadow_views,
        cfg=cfg,
        calibration=calibration,
        tf_weights=tf_weights,
        dqs_status=dqs_status,
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
        # Additive — bkz. _evidence_for_symbol; eski kayıtlarda alan yoksa boş kalır.
        evidence = s.get("evidence") or {}
        elliott_ev = evidence.get("elliott") or {}
        edge_ev = evidence.get("historical_edge") or {}
        # Additive — bkz. _setup_and_conflict_for_symbol; eski kayıtlarda yoksa boş kalır.
        setup_conflict = s.get("setup_conflict") or {}
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
                "elliott_scenario": elliott_ev.get("primary_scenario"),
                "elliott_confidence": elliott_ev.get("confidence"),
                "elliott_bias": elliott_ev.get("bias"),
                "historical_edge_sample_count": edge_ev.get("sample_count"),
                "historical_edge_win_rate": edge_ev.get("win_rate"),
                "historical_edge_confidence": edge_ev.get("edge_confidence"),
                "setup_type": setup_conflict.get("setup_type"),
                "setup_reason": setup_conflict.get("setup_reason"),
                "trade_profile": setup_conflict.get("trade_profile"),
                "mode_filter_passed": setup_conflict.get("mode_filter_passed"),
                "mode_filter_blocked_reason": setup_conflict.get("mode_filter_blocked_reason"),
                "conflict_final_action": setup_conflict.get("conflict_final_action"),
                "conflict_blocked_by": list(setup_conflict.get("conflict_blocked_by") or []),
                # Additive — fixed-% (live execution) vs adaptive ATR/S-R targets,
                # side-by-side; {} when unavailable (no side/ATR for this tick).
                "target_comparison": setup_conflict.get("target_comparison") or {},
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
