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
from pathlib import Path
from typing import Any

from packages.data.registry.loader import REPO_ROOT, load_thresholds


def _cfg() -> dict[str, Any]:
    return (load_thresholds().get("causal_world") or {}).get("calibration") or {}


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bucket(rows: list[dict[str, Any]], prior_strength: float, min_samples: int) -> dict[str, Any]:
    effects: list[float] = []
    hits = 0
    prior_sign = 1 if prior_strength >= 0 else -1
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
        recommended = round(max(-1.0, min(1.0, prior_strength * min(1.5, max(0.0, abs(observed))))), 6)
        recommended = abs(recommended) * prior_sign
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
        "recommended_strength": recommended,
        "recommendation_only": True,
    }


def calibrate_edges(rows: Iterable[dict[str, Any]], *, priors: dict[str, float] | None = None, min_samples: int | None = None) -> dict[str, Any]:
    """Measure edge evidence grouped by global/regime/horizon cells."""
    cfg = _cfg()
    minimum = int(min_samples or cfg.get("min_samples", 8))
    prior_map = priors or {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        edge = str(row.get("edge") or f"{row.get('source')}->{row.get('target')}")
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
        recommendations[key] = _bucket(values, prior, minimum)
    return {
        "status": "OK" if recommendations else "INSUFFICIENT",
        "min_samples": minimum,
        "recommendations": recommendations,
        "shadow_only": True,
        "auto_apply": False,
    }


def _path() -> Path:
    raw = Path(os.environ.get("CAUSAL_CALIBRATION_PATH", "data/runtime/causal_calibration.json"))
    return raw if raw.is_absolute() else REPO_ROOT / raw


def write_recommendations(rows: Iterable[dict[str, Any]], *, priors: dict[str, float] | None = None) -> dict[str, Any]:
    report = calibrate_edges(rows, priors=priors)
    payload = {**report, "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()}
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass
    return payload


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
            return {"weight": float(value), "weight_source": source, "sample_n": n, "confidence": min(1.0, n / max(1, minimum)), "regime": regime, "horizon": horizon}
    return {"weight": float(prior_strength), "weight_source": "PRIOR", "sample_n": 0, "confidence": 0.0, "regime": regime, "horizon": horizon}


# Explicit name for callers/tests that describe this as an empirical graph fit.
calibrate_causal_graph = calibrate_edges

__all__ = ["calibrate_causal_graph", "calibrate_edges", "load_recommendations", "resolve_weight", "write_recommendations"]
