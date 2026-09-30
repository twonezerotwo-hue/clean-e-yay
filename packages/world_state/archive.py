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

SCHEMA_VERSION = 1
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
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


def compact_record(world: Any, *, snapshot_id: str | None = None, asset_impacts: Any = (), causal_consensus: Any = ()) -> dict[str, Any]:
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
    record = {
        "schema_version": SCHEMA_VERSION,
        "causal_config_version": getattr(world, "causal_config_version", "v1.0"),
        "snapshot_id": snapshot_id,
        "generated_at": generated.isoformat() if hasattr(generated, "isoformat") else str(generated or ""),
        "snapshot_as_of": generated.isoformat() if hasattr(generated, "isoformat") else str(generated or ""),
        "available_events_as_of": generated.isoformat() if hasattr(generated, "isoformat") else str(generated or ""),
        "factors": factors,
        "flow_state": getattr(world, "flow_state", None) or {},
        "regime": getattr(world, "regime", None) or getattr(world, "global_flow_regime", "UNKNOWN"),
        "event_ids": [getattr(item, "event_id", None) for item in getattr(world, "geopolitical_events", ()) if getattr(item, "event_id", None)],
        "statement_ids": [getattr(item, "statement_id", None) for item in getattr(world, "statements", ()) if getattr(item, "statement_id", None)],
        "expectation_ids": [item.subject for item in getattr(world, "expectations", ()) if getattr(item, "subject", None)],
        "macro_event_ids": [getattr(item, "event_id", None) for item in getattr(world, "macro_surprises", ()) if getattr(item, "event_id", None)],
        "interactions": [item.to_dict() for item in getattr(world, "interactions", ())],
        "asset_impacts": impacts,
        "causal_consensus": consensus,
        "factor_confidence": getattr(world, "confidence", None),
        "factor_coverage": getattr(world, "coverage", None),
        "factor_provenance": getattr(world, "macro_sources", None),
    }
    record["record_fingerprint"] = _fingerprint(record)
    return record


def record(world: Any, *, snapshot_id: str | None = None, asset_impacts: Any = (), causal_consensus: Any = (), now: datetime | None = None) -> dict[str, Any] | None:
    """Append one material World-State row, deduplicating unchanged state."""
    row = compact_record(world, snapshot_id=snapshot_id, asset_impacts=asset_impacts, causal_consensus=causal_consensus)
    row["archived_at"] = (now or datetime.now(UTC)).isoformat()
    with _LOCK:
        rows = _read()
        if rows and rows[-1].get("record_fingerprint") == row["record_fingerprint"]:
            return None
        rows.append(row)
        cfg = _cfg()
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


__all__ = ["SCHEMA_VERSION", "all_records", "compact_record", "record", "status"]
