"""Deterministic scenario probabilities with explicit evidence provenance."""
from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from packages.scenarios.model import ScenarioReport, ScenarioResult

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "scenarios_v1.0.yaml"


def _path() -> Path:
    raw = os.environ.get("SCENARIOS_CONFIG_PATH", str(_DEFAULT_PATH))
    return Path(raw) if Path(raw).is_absolute() else Path(__file__).resolve().parents[2] / raw


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _load() -> tuple[str, set[str], list[dict[str, Any]]]:
    try:
        raw = yaml.safe_load(_path().read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return "unavailable", set(), []
    scenarios = [dict(item) for item in raw.get("scenarios") or () if isinstance(item, Mapping) and item.get("id")]
    return str(raw.get("version") or "unknown"), set(str(x) for x in raw.get("event_types") or ()), scenarios


def _event_value(event: Any, key: str, default: Any = None) -> Any:
    return event.get(key, default) if isinstance(event, Mapping) else getattr(event, key, default)


def _evidence(event: Any) -> tuple[dict[str, float], tuple[str, ...]]:
    values = {
        "severity": _number(_event_value(event, "severity")) or 0.0,
        "source_confidence": _number(_event_value(event, "source_confidence")) or 0.0,
        "confirmation": min(1.0, max(0.0, _number(_event_value(event, "confirmation_count")) or 0.0) / 3.0),
        "official": 1.0 if bool(_event_value(event, "official_confirmation")) else 0.0,
        "decay": _number(_event_value(event, "decay_factor")) or 0.0,
    }
    used = tuple(key for key, value in values.items() if value > 0)
    return values, used


def _score(scenario: Mapping[str, Any], evidence: Mapping[str, float]) -> float:
    class_name = str(scenario.get("class") or "PERSISTENCE").upper()
    base = max(1e-9, _number(scenario.get("prior_probability")) or 0.0)
    severity = evidence.get("severity", 0.0)
    confirmation = evidence.get("confirmation", 0.0)
    official = evidence.get("official", 0.0)
    decay = evidence.get("decay", 0.0)
    if class_name == "ESCALATION":
        modifier = 1.0 + 0.80 * severity + 0.35 * confirmation + 0.20 * official
    elif class_name == "DEESCALATION":
        modifier = 1.0 + 0.25 * (1.0 - severity) + 0.15 * (1.0 - confirmation)
    else:
        modifier = 1.0 + 0.35 * (1.0 - severity) + 0.20 * decay
    return base * max(0.05, modifier)


def _for_event(event: Any, definitions: list[dict[str, Any]]) -> tuple[ScenarioResult, ...]:
    event_id = str(_event_value(event, "event_id", "") or "")
    evidence, evidence_used = _evidence(event)
    scored = [(item, _score(item, evidence)) for item in definitions]
    total = sum(score for _, score in scored)
    if total <= 0:
        return ()
    source = "EVIDENCE_ADJUSTED" if evidence_used else "PRIOR_ONLY"
    rows: list[ScenarioResult] = []
    for item, score in scored:
        directions = {str(key): float(value) for key, value in (item.get("asset_direction") or {}).items()}
        rows.append(ScenarioResult(
            event_id=event_id,
            scenario_id=str(item["id"]),
            name=str(item.get("name") or item["id"]),
            probability=round(score / total, 6),
            probability_source=source,
            class_name=str(item.get("class") or "PERSISTENCE"),
            horizon=str(item.get("horizon") or "unknown"),
            affected_assets=directions,
            factor_channels=tuple(str(x) for x in item.get("factor_channels") or ()),
            invalidators=tuple(str(x) for x in item.get("invalidators") or ()),
            evidence_used=evidence_used,
            warnings=("prior_only_no_runtime_evidence",) if not evidence_used else (),
        ))
    # Floating-point normalisation keeps the distribution exactly auditable.
    correction = round(1.0 - sum(row.probability for row in rows), 6)
    if rows and correction:
        top = max(range(len(rows)), key=lambda index: rows[index].probability)
        row = rows[top]
        rows[top] = ScenarioResult(**{**row.to_dict(), "probability": round(row.probability + correction, 6)})
    return tuple(rows)


def build_report(events: Iterable[Any] = ()) -> ScenarioReport:
    """Build scenario distributions for supported event types only."""
    version, supported, definitions = _load()
    if not definitions:
        return ScenarioReport(version, "UNAVAILABLE", warnings=("scenario_config_unavailable",))
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for event in events or ():
        event_type = str(_event_value(event, "event_type", "UNKNOWN") or "UNKNOWN").upper()
        event_id = str(_event_value(event, "event_id", "") or "")
        if supported and event_type not in supported:
            warnings.append(f"scenario_event_type_unsupported:{event_type}")
            continue
        results = _for_event(event, definitions)
        if results:
            rows.append({"event_id": event_id, "event_type": event_type, "scenarios": [row.to_dict() for row in results]})
    status = "OK" if rows else "NO_MATCH"
    return ScenarioReport(version, status, tuple(rows), tuple(dict.fromkeys(warnings)))


__all__ = ["build_report"]
