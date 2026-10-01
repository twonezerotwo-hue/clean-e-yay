"""Compact historical World-State archive adapter.

This reuses the repository's file-backed runtime convention (JSONL + atomic
rewrite for retention) and stores references/derived fields only.  It is an
observation store: it never fetches data, changes decisions, or promotes
weights.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.data.registry.loader import REPO_ROOT, load_thresholds

SCHEMA_VERSION = 2
_LOCK = threading.Lock()


def _path() -> Path:
    raw = Path(os.environ.get("WORLD_STATE_ARCHIVE_PATH", "data/runtime/world_state_archive.jsonl"))
    return raw if raw.is_absolute() else REPO_ROOT / raw


def _cfg() -> dict[str, Any]:
    try:
        return (load_thresholds().get("causal_world") or {}).get("archive") or {}
    except Exception:
        return {}


def _read() -> list[dict[str, Any]]:
    try:
        path = _path()
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
            except (ValueError, TypeError):
                continue
        return rows
    except OSError:
        return []


def _fingerprint(record: dict[str, Any]) -> str:
    material = {
        "factors": record.get("factors"),
        "flow_state": record.get("flow_state"),
        "regime": record.get("regime"),
        "event_ids": record.get("event_ids"),
        "statement_ids": record.get("statement_ids"),
        "expectation_ids": record.get("expectation_ids"),
        "interaction_count": len(record.get("interactions") or []),
        "graph_context": {
            "graph_version": (record.get("graph_context") or {}).get("graph_version"),
            "entity_ids": (record.get("graph_context") or {}).get("entity_ids"),
            "affected_assets": (record.get("graph_context") or {}).get("affected_assets"),
        },
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


_MATERIAL_FACTORS = (
    "liquidity", "usd_pressure", "rates_pressure", "real_yield_pressure",
    "inflation_pressure", "growth_pressure", "risk_aversion", "credit_stress",
    "energy_supply_risk", "shipping_risk", "trade_risk", "sanctions_pressure",
)


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    else:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else None


def _provenance(world: Any, generated: Any, explicit: dict[str, Any] | None = None) -> dict[str, Any]:
    supplied = getattr(world, "provenance", None) or {}
    supplied = {**supplied, **(explicit or {})}
    raw_domains = supplied.get("domains") or supplied.get("provenance_domains") or {}
    domains = {
        str(name): {
            "status": str((value or {}).get("status", "UNKNOWN")).upper(),
            "as_of": _iso((value or {}).get("as_of")),
        }
        for name, value in raw_domains.items()
        if isinstance(value, dict)
    }
    # Only snapshot_as_of can safely fall back to the derived snapshot time.
    # Other domains remain unavailable unless the ingestion layer supplied a
    # real watermark.
    return {
        "snapshot_as_of": _iso(supplied.get("snapshot_as_of") or generated),
        "market_data_as_of": _iso(supplied.get("market_data_as_of")),
        "events_available_as_of": _iso(supplied.get("events_available_as_of")),
        "statements_available_as_of": _iso(supplied.get("statements_available_as_of")),
        "macro_available_as_of": _iso(supplied.get("macro_available_as_of")),
        "expectations_as_of": _iso(supplied.get("expectations_as_of")),
        "flow_available_as_of": _iso(supplied.get("flow_available_as_of")),
        "ingested_at": _iso(supplied.get("ingested_at")),
        "provenance_domains": domains,
    }


def _material_changes(previous: dict[str, Any] | None, current: dict[str, Any], epsilon: float) -> list[str]:
    if not previous:
        return ["INITIAL_SNAPSHOT"]
    changes: list[str] = []
    old_factors = previous.get("factors") or {}
    new_factors = current.get("factors") or {}
    for name in _MATERIAL_FACTORS:
        old, new = old_factors.get(name), new_factors.get(name)
        if old is None or new is None:
            if old != new:
                changes.append(f"FACTOR:{name}")
        else:
            try:
                if abs(float(new) - float(old)) >= epsilon:
                    changes.append(f"FACTOR:{name}")
            except (TypeError, ValueError):
                if old != new:
                    changes.append(f"FACTOR:{name}")
    if previous.get("regime") != current.get("regime"):
        changes.append("REGIME_CHANGE")
    for label in ("event_ids", "statement_ids", "macro_event_ids", "expectation_ids"):
        old_ids = set(previous.get(label) or ())
        new_ids = set(current.get(label) or ())
        if new_ids - old_ids:
            changes.append(f"NEW_{label.upper()}")
    def _nested_material(old: Any, new: Any) -> bool:
        if isinstance(old, dict) and isinstance(new, dict):
            return any(_nested_material(old.get(key), new.get(key)) for key in set(old) | set(new))
        if isinstance(old, (list, tuple)) and isinstance(new, (list, tuple)):
            if len(old) != len(new):
                return True
            return any(_nested_material(left, right) for left, right in zip(old, new, strict=True))
        if old is None or new is None:
            return old != new
        try:
            return abs(float(new) - float(old)) >= epsilon
        except (TypeError, ValueError):
            return old != new
    if _nested_material(previous.get("flow_state"), current.get("flow_state")):
        changes.append("FLOW_CHANGE")
    if _nested_material(previous.get("expectations"), current.get("expectations")):
        changes.append("EXPECTATION_CHANGE")
    if previous.get("interactions") != current.get("interactions"):
        changes.append("INTERACTION_CHANGE")
    return changes


def compact_record(
    world: Any,
    *,
    snapshot_id: str | None = None,
    asset_impacts: Any = (),
    causal_consensus: Any = (),
    edges: Any = (),
    forecasts: Any = (),
    provenance: dict[str, Any] | None = None,
    reconstruction_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a compact, reference-oriented archive row from a snapshot."""
    factors = {
        name: getattr(world, name, None)
        for name in (
            "liquidity", "usd_pressure", "rates_pressure", "real_yield_pressure",
            "inflation_pressure", "growth_pressure", "risk_aversion", "credit_stress",
            "energy_supply_risk", "shipping_risk", "sanctions_pressure", "trade_risk",
            "oil_pressure", "geopolitical_risk", "crypto_liquidity", "equity_risk_appetite",
        )
        if getattr(world, name, None) is not None
    }
    impacts = []
    for impact in asset_impacts or ():
        item = impact if isinstance(impact, dict) else impact.to_dict()
        impacts.append({
            key: item.get(key)
            for key in ("symbol", "direction_score", "confidence", "time_horizon", "base_thesis_score", "drivers", "entry_quality", "timing_status")
            if item.get(key) is not None
        })
    consensus = []
    for row in causal_consensus or ():
        if isinstance(row, dict):
            consensus.append({key: row.get(key) for key in ("symbol", "timeframe", "world_thesis_score", "world_thesis_direction", "entry_timing_state", "final_shadow_score_tf", "final_shadow_direction")})
    generated = getattr(world, "generated_at", None)
    domain_provenance = _provenance(world, generated, provenance)
    edge_rows = []
    for edge in edges or ():
        item = edge if isinstance(edge, dict) else edge.to_dict()
        edge_id = item.get("edge_id")
        if not edge_id and item.get("source") and item.get("target"):
            from packages.causal.engine import canonical_edge_id
            edge_id = canonical_edge_id(str(item["source"]), str(item["target"]))
        edge_rows.append({key: item.get(key) for key in (
            "source", "target", "sign", "source_value", "contribution", "weight",
            "prior_strength", "weight_source", "sample_n", "confidence",
            "confidence_interval", "regime", "horizon", "applied",
        ) if item.get(key) is not None} | {"edge_id": edge_id})
    forecast_rows = []
    for forecast in forecasts or ():
        item = forecast if isinstance(forecast, dict) else forecast.to_dict()
        # Keep the archive compact and replayable: all quantiles are retained,
        # while no provider payload or order instruction is copied.
        forecast_rows.append({key: item.get(key) for key in (
            "symbol", "horizon", "as_of", "current_price", "point_estimate",
            "p10", "p25", "p50", "p75", "p90", "directional_bias",
            "confidence", "volatility_abs", "volatility_source", "method",
            "available", "missing_inputs", "warnings",
        ) if key in item})
    record = {
        "schema_version": SCHEMA_VERSION,
        "causal_config_version": getattr(world, "causal_config_version", "v1.0"),
        "snapshot_id": snapshot_id,
        "generated_at": generated.isoformat() if hasattr(generated, "isoformat") else str(generated or ""),
        "snapshot_as_of": domain_provenance["snapshot_as_of"],
        "market_data_as_of": domain_provenance["market_data_as_of"],
        "events_available_as_of": domain_provenance["events_available_as_of"],
        "statements_available_as_of": domain_provenance["statements_available_as_of"],
        "macro_available_as_of": domain_provenance["macro_available_as_of"],
        "expectations_as_of": domain_provenance["expectations_as_of"],
        "flow_available_as_of": domain_provenance["flow_available_as_of"],
        "ingested_at": domain_provenance["ingested_at"],
        "provenance_domains": domain_provenance["provenance_domains"],
        # Backward-compatible alias; unlike the old implementation it is not
        # fabricated from generated_at.
        "available_events_as_of": domain_provenance["events_available_as_of"],
        "factors": factors,
        "flow_state": getattr(world, "flow_state", None) or {},
        "regime": getattr(world, "regime", None) or getattr(world, "global_flow_regime", "UNKNOWN"),
        "event_ids": [getattr(item, "event_id", None) for item in getattr(world, "geopolitical_events", ()) if getattr(item, "event_id", None)],
        "statement_ids": [getattr(item, "statement_id", None) for item in getattr(world, "statements", ()) if getattr(item, "statement_id", None)],
        "expectation_ids": [item.subject for item in getattr(world, "expectations", ()) if getattr(item, "subject", None)],
        "expectations": [
            {
                "subject": item.subject,
                "expected_value": item.expected_value,
                "actual_value": item.actual_value,
                "surprise": item.surprise,
                "as_of": _iso(item.as_of),
            }
            for item in getattr(world, "expectations", ())
        ],
        "macro_event_ids": [getattr(item, "event_id", None) for item in getattr(world, "macro_surprises", ()) if getattr(item, "event_id", None)],
        "interactions": [item.to_dict() for item in getattr(world, "interactions", ())],
        "graph_context": getattr(world, "graph_context", None),
        "physical_commodity": getattr(world, "physical_commodity", None),
        "scenario_report": getattr(world, "scenario_report", None),
        "asset_discovery": getattr(world, "asset_discovery", None),
        "asset_impacts": impacts,
        "causal_consensus": consensus,
        "factor_confidence": getattr(world, "confidence", None),
        "factor_coverage": getattr(world, "coverage", None),
        "factor_provenance": getattr(world, "macro_sources", None),
        "edge_predictions": edge_rows,
        "forecast_bands": forecast_rows,
        "data_verified": str(getattr(world, "data_quality", "UNAVAILABLE")) not in {"UNAVAILABLE", "INVALID"},
        "reconstruction_inputs": reconstruction_inputs,
    }
    record["record_fingerprint"] = _fingerprint(record)
    return record


def record(
    world: Any,
    *,
    snapshot_id: str | None = None,
    asset_impacts: Any = (),
    causal_consensus: Any = (),
    edges: Any = (),
    forecasts: Any = (),
    provenance: dict[str, Any] | None = None,
    reconstruction_inputs: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Append a cadence/material World-State row.

    The writer remains observation-only.  A material factor/event/regime
    change bypasses cadence; an unchanged state writes only a periodic
    checkpoint.  The bounded on-disk archive remains the restart-safe source
    of truth and is only rewritten when one of those rules permits a row.
    """
    row = compact_record(
        world, snapshot_id=snapshot_id, asset_impacts=asset_impacts,
        causal_consensus=causal_consensus, edges=edges, forecasts=forecasts,
        provenance=provenance, reconstruction_inputs=reconstruction_inputs,
    )
    archived_at = now or datetime.now(UTC)
    row["archived_at"] = archived_at.isoformat()
    with _LOCK:
        rows = _read()
        cfg = _cfg()
        try:
            cadence = max(0.0, float(cfg.get("cadence_seconds", 300)))
        except (TypeError, ValueError):
            cadence = 300.0
        try:
            epsilon = max(0.0, float(cfg.get("material_change_epsilon", 0.02)))
        except (TypeError, ValueError):
            epsilon = 0.02
        previous = rows[-1] if rows else None
        changes = _material_changes(previous, row, epsilon)
        previous_time = _dt((previous or {}).get("archived_at"))
        elapsed = (archived_at.astimezone(UTC) - previous_time).total_seconds() if previous_time else None
        material = bool(changes)
        due = previous is None or material or elapsed is None or elapsed >= cadence
        if not due:
            return None
        if material:
            if "REGIME_CHANGE" in changes:
                reason = "REGIME_CHANGE"
            elif any(item.startswith("NEW_") for item in changes):
                reason = "NEW_EVIDENCE"
            elif any(item.startswith("FACTOR:") for item in changes):
                reason = "MATERIAL_CHANGE"
            else:
                reason = "MATERIAL_CHANGE"
        else:
            reason = "CADENCE_CHECKPOINT"
        row["archive_write_reason"] = reason
        row["material_changes"] = changes
        row["checkpoint"] = reason == "CADENCE_CHECKPOINT"
        rows.append(row)
        try:
            max_rows = max(1, int(cfg.get("max_snapshots", os.environ.get("WORLD_STATE_ARCHIVE_MAX", 5000))))
        except (TypeError, ValueError):
            max_rows = 5000
        cutoff_days = cfg.get("retention_days")
        if cutoff_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=float(cutoff_days))
            keep: list[dict[str, Any]] = []
            for item in rows:
                try:
                    ts = datetime.fromisoformat(str(item.get("generated_at", "")).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    if ts >= cutoff:
                        keep.append(item)
                except (TypeError, ValueError):
                    keep.append(item)
            rows = keep
        rows = rows[-max_rows:]
        path = _path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
            tmp.write_text("\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in rows) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            return None
    return row


def all_records() -> list[dict[str, Any]]:
    return _read()


def materialize_edge_outcomes(
    rows: list[dict[str, Any]] | None = None,
    *,
    horizons: tuple[str, ...] = ("15m", "1h", "4h", "1d"),
) -> dict[str, Any]:
    """Turn archived edge predictions into matured factor-response rows.

    This is intentionally a small adapter over the canonical archive, not a
    second history store.  Future state is read only when its archived
    timestamp is at/after the requested horizon; pending outcomes remain
    pending and are never fabricated.
    """
    source_rows = sorted(list(rows if rows is not None else _read()), key=lambda item: str(item.get("generated_at") or ""))
    seconds = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
    output: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    seen: set[tuple[Any, ...]] = set()
    for index, current in enumerate(source_rows):
        prediction_at = _dt(current.get("snapshot_as_of") or current.get("generated_at"))
        if prediction_at is None:
            rejected["bad_prediction_timestamp"] = rejected.get("bad_prediction_timestamp", 0) + 1
            continue
        edges = current.get("edge_predictions") or []
        if not isinstance(edges, list):
            continue
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            source_value = edge.get("source_value")
            source_name, target_name = edge.get("source"), edge.get("target")
            if source_name is None or target_name is None or source_value is None:
                rejected["missing_prediction"] = rejected.get("missing_prediction", 0) + 1
                continue
            edge_id = edge.get("edge_id")
            if not edge_id:
                from packages.causal.engine import canonical_edge_id
                edge_id = canonical_edge_id(str(source_name), str(target_name))
            edge_key = str(edge_id)
            event_ids = tuple(sorted(set(current.get("event_ids") or ()) | set(current.get("macro_event_ids") or ())))
            root_event_ids = tuple(current.get("root_event_ids") or event_ids)
            if not root_event_ids:
                root_event_ids = ("WORLD_STATE",)
            for horizon in horizons:
                horizon_seconds = seconds.get(str(horizon))
                if horizon_seconds is None:
                    continue
                # One matured sample per edge/root/horizon.  This prevents
                # repeated worker checkpoints from inflating N.
                dedup = (
                    edge_key,
                    root_event_ids,
                    str(horizon),
                    prediction_at.isoformat() if root_event_ids == ("WORLD_STATE",) else None,
                )
                if dedup in seen:
                    continue
                future = None
                for candidate in source_rows[index + 1:]:
                    candidate_at = _dt(candidate.get("snapshot_as_of") or candidate.get("generated_at"))
                    if candidate_at is None or (candidate_at - prediction_at).total_seconds() < horizon_seconds:
                        continue
                    future = candidate
                    break
                if future is None:
                    continue
                outcome_at = _dt(future.get("snapshot_as_of") or future.get("generated_at"))
                factors = future.get("factors") or {}
                old_target = (current.get("factors") or {}).get(target_name)
                new_target = factors.get(target_name)
                if old_target is None or new_target is None:
                    rejected["missing_target_outcome"] = rejected.get("missing_target_outcome", 0) + 1
                    continue
                try:
                    response = float(new_target) - float(old_target)
                    source_numeric = float(source_value)
                except (TypeError, ValueError):
                    rejected["non_numeric_outcome"] = rejected.get("non_numeric_outcome", 0) + 1
                    continue
                verified = bool(current.get("data_verified")) and bool(future.get("data_verified"))
                seen.add(dedup)
                output.append({
                    "edge": edge_key,
                    "edge_id": edge_key,
                    "source": source_name,
                    "target": target_name,
                    "sign": int(edge.get("sign", 1) or 1),
                    "source_value": source_numeric,
                    "target_response": round(response, 8),
                    "regime": current.get("regime") or "UNKNOWN",
                    "horizon": str(horizon),
                    "event_id": event_ids[0] if len(event_ids) == 1 else None,
                    "root_event_ids": list(root_event_ids),
                    "prediction_as_of": prediction_at.isoformat(),
                    "outcome_as_of": outcome_at.isoformat() if outcome_at else None,
                    "data_verified": verified,
                    "prior_strength": edge.get("prior_strength", edge.get("weight", 0.5)),
                    "outcome_method": "archived_factor_delta",
                })
    return {"rows": output, "rejected": rejected, "raw_rows": len(output) + sum(rejected.values()), "pending": True}


def status() -> dict[str, Any]:
    rows = _read()
    return {
        "status": "OK" if rows else "INSUFFICIENT_ARCHIVE",
        "records": len(rows),
        "archive_start": rows[0].get("generated_at") if rows else None,
        "archive_end": rows[-1].get("generated_at") if rows else None,
        "schema_version": SCHEMA_VERSION,
        "path": str(_path()),
    }


__all__ = ["SCHEMA_VERSION", "all_records", "compact_record", "materialize_edge_outcomes", "record", "status"]
