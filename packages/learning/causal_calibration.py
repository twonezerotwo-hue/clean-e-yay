"""Shadow calibration of causal edge priors.

The module measures factor-to-factor evidence and returns recommendations.  It
never edits YAML, activates a weight, or changes the decision path.  Grouping
supports global, regime, horizon, and regime+horizon cells with an explicit
sample-gated fallback hierarchy.
"""
from __future__ import annotations

import json
import math
import os
import statistics
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.data.registry.loader import REPO_ROOT, load_thresholds
from packages.ops.store import write_text_atomic


def _cfg() -> dict[str, Any]:
    return (load_thresholds().get("causal_world") or {}).get("calibration") or {}


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bucket(rows: list[dict[str, Any]], prior_strength: float, min_samples: int, edge_sign: int | None = None) -> dict[str, Any]:
    effects: list[float] = []
    hits = 0
    prior_sign = edge_sign if edge_sign in {-1, 1} else (1 if prior_strength >= 0 else -1)
    prior_strength = abs(float(prior_strength))
    for row in rows:
        source = _num(row.get("source_value"))
        target = _num(row.get("target_response", row.get("observed_effect")))
        if source is None or target is None or source == 0:
            continue
        effects.append(target / source)
        hits += int(source * target * prior_sign > 0)
    n = len(effects)
    observed = statistics.fmean(effects) if effects else None
    median = statistics.median(effects) if effects else None
    hit_rate = hits / n if n else None
    if n:
        stdev = statistics.pstdev(effects) if n > 1 else 0.0
        margin = 1.96 * stdev / math.sqrt(n)
        ci = [round(observed - margin, 6), round(observed + margin, 6)]
    else:
        ci = [None, None]
    sign = (1 if observed is not None and observed > 0 else -1 if observed is not None and observed < 0 else 0)
    sign_conflict = bool(sign and sign != prior_sign)
    stable = n >= min_samples and not sign_conflict and (hit_rate or 0.0) >= 0.5
    recommended = None
    if n >= min_samples and observed is not None and not sign_conflict:
        # Direction belongs to the topology ``sign`` field.  The calibrated
        # recommendation is magnitude only; returning a negative weight here
        # would make the graph multiply by ``sign`` a second time.
        recommended = round(max(0.0, min(1.0, prior_strength * min(1.5, max(0.0, abs(observed))))), 6)
    return {
        "n": n,
        "prior_sign": prior_sign,
        "prior_strength": round(abs(prior_strength), 6),
        "observed_sign": sign or None,
        "observed_effect": round(observed, 6) if observed is not None else None,
        "hit_rate": round(hit_rate, 6) if hit_rate is not None else None,
        "median_effect": round(median, 6) if median is not None else None,
        "confidence_interval": ci,
        "stability": "STABLE" if stable else "UNSTABLE_EDGE" if sign_conflict else "INSUFFICIENT",
        "sign_conflict": sign_conflict,
        "sign": prior_sign,
        "recommended_strength": recommended,
        "recommendation_only": True,
    }


def _valid_row(row: dict[str, Any]) -> tuple[bool, str | None]:
    """Quality gate for evidence; rejected rows must not increase sample N."""
    if row.get("data_verified") is not True:
        return False, "unverified_source"
    for name in ("source_value", "target_response"):
        if _num(row.get(name)) is None:
            return False, f"missing_{name}"
    if _num(row.get("source_value")) == 0.0:
        return False, "zero_source_value"
    if not row.get("prediction_as_of") or not row.get("outcome_as_of"):
        return False, "missing_timestamp"
    try:
        prediction = datetime.fromisoformat(str(row["prediction_as_of"]).replace("Z", "+00:00"))
        outcome = datetime.fromisoformat(str(row["outcome_as_of"]).replace("Z", "+00:00"))
        if prediction.tzinfo is None:
            prediction = prediction.replace(tzinfo=UTC)
        if outcome.tzinfo is None:
            outcome = outcome.replace(tzinfo=UTC)
        if outcome <= prediction:
            return False, "future_leakage_or_bad_timestamp"
    except (TypeError, ValueError):
        return False, "bad_timestamp"
    if row.get("expired"):
        return False, "expired_event"
    if row.get("valid_until"):
        try:
            valid_until = datetime.fromisoformat(str(row["valid_until"]).replace("Z", "+00:00"))
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=UTC)
            if valid_until <= outcome:
                return False, "expired_event"
        except (TypeError, ValueError):
            return False, "bad_timestamp"
    return True, None


def _quality_filter(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int], int]:
    eligible: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    raw = 0
    seen: set[tuple[Any, ...]] = set()
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        raw += 1
        ok, reason = _valid_row(row)
        if not ok:
            key = reason or "invalid"
            rejected[key] = rejected.get(key, 0) + 1
            continue
        roots = tuple(sorted(set(row.get("root_event_ids") or ([row.get("event_id")] if row.get("event_id") else ["WORLD_STATE"]))))
        dedup = (row.get("edge"), roots, row.get("horizon"), row.get("prediction_as_of"))
        if dedup in seen:
            rejected["duplicate_root_horizon"] = rejected.get("duplicate_root_horizon", 0) + 1
            continue
        seen.add(dedup)
        eligible.append(row)
    return eligible, rejected, raw


def calibrate_edges(rows: Iterable[dict[str, Any]], *, priors: dict[str, float] | None = None, min_samples: int | None = None) -> dict[str, Any]:
    """Measure edge evidence grouped by global/regime/horizon cells."""
    cfg = _cfg()
    minimum = int(min_samples or cfg.get("min_samples", 8))
    prior_map = priors or {}
    eligible, rejection_reasons, raw_rows = _quality_filter(rows)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        edge = str(row.get("edge_id") or row.get("edge") or f"{row.get('source')}->{row.get('target')}")
        if edge in {"None->None", "->"}:
            continue
        groups.setdefault(f"{edge}|GLOBAL|ALL", []).append(row)
        regime = str(row.get("regime") or "UNKNOWN")
        horizon = str(row.get("horizon") or "ALL")
        groups.setdefault(f"{edge}|REGIME:{regime}|ALL", []).append(row)
        groups.setdefault(f"{edge}|GLOBAL|HORIZON:{horizon}", []).append(row)
        groups.setdefault(f"{edge}|REGIME:{regime}|HORIZON:{horizon}", []).append(row)
    recommendations: dict[str, dict[str, Any]] = {}
    for key, values in sorted(groups.items()):
        edge = key.split("|", 1)[0]
        prior = float(prior_map.get(edge, values[0].get("prior_strength", 0.5) or 0.5))
        edge_sign = int(values[0].get("sign", 0) or 0)
        recommendations[key] = _bucket(values, prior, minimum, edge_sign=edge_sign or None)
    return {
        "status": "OK" if recommendations else "INSUFFICIENT",
        "min_samples": minimum,
        "raw_rows": raw_rows,
        "eligible_rows": len(eligible),
        "rejected_rows": raw_rows - len(eligible),
        "rejection_reasons": rejection_reasons,
        "recommendations": recommendations,
        "shadow_only": True,
        "auto_apply": False,
    }


def _path() -> Path:
    raw = Path(os.environ.get("CAUSAL_CALIBRATION_PATH", "data/runtime/causal_calibration.json"))
    return raw if raw.is_absolute() else REPO_ROOT / raw


def write_recommendations(rows: Iterable[dict[str, Any]], *, priors: dict[str, float] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    report = calibrate_edges(rows, priors=priors)
    payload = {**report, **(metadata or {}), "generated_at": datetime.now(UTC).isoformat()}
    try:
        path = _path()
        write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))
    except OSError:
        pass
    return payload


def run_if_due(*, now: datetime | None = None, force: bool = False) -> dict[str, Any]:
    """Off-tick calibration loop over matured archive outcomes.

    Artifact freshness gates archive parsing.  This function is safe to call
    from every worker cycle and never mutates decisions or graph config.
    """
    now = now or datetime.now(UTC)
    cfg = _cfg()
    if not bool(cfg.get("enabled", True)):
        return {"status": "DISABLED", "raw_rows": 0, "eligible_rows": 0}
    path = _path()
    try:
        interval = max(0.0, float(cfg.get("interval_seconds", 300) or 300))
    except (TypeError, ValueError):
        interval = 300.0
    try:
        artifact_time = datetime.fromtimestamp(path.stat().st_mtime, UTC) if path.exists() else None
        archive_raw = Path(os.environ.get("WORLD_STATE_ARCHIVE_PATH", "data/runtime/world_state_archive.jsonl"))
        archive_path = archive_raw if archive_raw.is_absolute() else REPO_ROOT / archive_raw
        archive_time = datetime.fromtimestamp(archive_path.stat().st_mtime, UTC) if archive_path.exists() else None
        archive_changed = bool(archive_time and (artifact_time is None or archive_time > artifact_time))
        if not force and artifact_time and not archive_changed and (now - artifact_time).total_seconds() < interval:
            return {"status": "SKIPPED_NOT_DUE", "generated_at": artifact_time.isoformat()}
    except OSError:
        artifact_time = None
    from packages.world_state.archive import all_records, materialize_edge_outcomes
    rows = all_records()
    materialized = materialize_edge_outcomes(rows)
    archive_window = {
        "start": rows[0].get("generated_at") if rows else None,
        "end": rows[-1].get("generated_at") if rows else None,
    }
    metadata = {
        "archive_window": archive_window,
        "rows_seen": materialized.get("raw_rows", 0),
        "rows_used": len(materialized.get("rows") or []),
        "runtime_loop": True,
        "auto_apply": False,
        "shadow_only": True,
    }
    return write_recommendations(materialized.get("rows") or [], metadata=metadata)


def load_recommendations() -> dict[str, Any]:
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def resolve_weight(edge: str, prior_strength: float, *, regime: str | None = None, horizon: str | None = None, recommendations: dict[str, Any] | None = None, min_samples: int | None = None) -> dict[str, Any]:
    """Resolve metadata only; default is always the prior unless evidence is sufficient."""
    cfg = _cfg()
    minimum = int(min_samples or cfg.get("min_samples", 8))
    data = recommendations if recommendations is not None else load_recommendations()
    recs = data.get("recommendations") or {}
    candidates = []
    if regime and horizon:
        candidates.append((f"{edge}|REGIME:{regime}|HORIZON:{horizon}", "REGIME_HORIZON_CALIBRATED"))
    if horizon:
        candidates.append((f"{edge}|GLOBAL|HORIZON:{horizon}", "HORIZON_CALIBRATED"))
    if regime:
        candidates.append((f"{edge}|REGIME:{regime}|ALL", "REGIME_CALIBRATED"))
    candidates.append((f"{edge}|GLOBAL|ALL", "GLOBAL_CALIBRATED"))
    for key, source in candidates:
        item = recs.get(key) or {}
        n = int(item.get("n", 0) or 0)
        value = item.get("recommended_strength")
        if n >= minimum and value is not None and not item.get("sign_conflict"):
            return {
                # Artifacts are magnitude-only by contract.  Keep this guard
                # for old/manual artifacts that may still contain a signed
                # recommendation; topology sign is applied by the graph.
                "weight": abs(float(value)),
                "weight_source": source,
                "sample_n": n,
                "confidence": min(1.0, n / max(1, minimum)),
                "confidence_interval": item.get("confidence_interval"),
                "regime": regime,
                "horizon": horizon,
            }
    return {"weight": float(prior_strength), "weight_source": "PRIOR", "sample_n": 0, "confidence": 0.0, "regime": regime, "horizon": horizon}


# Explicit name for callers/tests that describe this as an empirical graph fit.
calibrate_causal_graph = calibrate_edges

__all__ = ["calibrate_causal_graph", "calibrate_edges", "load_recommendations", "resolve_weight", "run_if_due", "write_recommendations"]
