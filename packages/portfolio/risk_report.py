"""Deterministic portfolio concentration and thesis-alignment report.

This module reads the paper ledger and asset registry only.  It does not
rebalance, close, size, or otherwise mutate portfolio state.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from packages.data.registry import assets as asset_registry


@dataclass(frozen=True)
class PortfolioRiskReport:
    generated_at: str
    status: str
    equity_usd: float
    gross_exposure_usd: float
    net_exposure_usd: float
    gross_exposure_pct: float | None
    net_exposure_pct: float | None
    max_symbol_weight: float | None
    concentration_hhi: float | None
    symbol_exposure: dict[str, dict[str, float]]
    theme_exposure: dict[str, dict[str, float]]
    thesis_conflicts: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    execution: str = "NO_EXECUTION"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if value == value and abs(value) != float("inf") else default


def _maybe_num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def _position_value(position: Any) -> tuple[str, str, float]:
    symbol = str(getattr(position, "symbol", "") or "").upper()
    side = str(getattr(position, "side", "") or "").lower()
    size = abs(_num(getattr(position, "size_usd", 0.0)))
    return symbol, side, size


def build_portfolio_risk(
    paper_state: Any,
    *,
    impacts: Mapping[str, Any] | Iterable[Any] = (),
    now: datetime | None = None,
) -> PortfolioRiskReport:
    """Return exposure metrics without changing the ledger or risk gate."""
    generated = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    equity = _num(getattr(paper_state, "equity_usd", 0.0))
    positions = list(getattr(paper_state, "open_positions", ()) or ())
    by_symbol: dict[str, dict[str, float]] = {}
    by_theme: dict[str, dict[str, float]] = {}
    net = 0.0
    gross = 0.0
    conflicts: list[dict[str, Any]] = []
    for position in positions:
        symbol, side, size = _position_value(position)
        if not symbol or size <= 0:
            continue
        signed = size if side == "long" else -size if side == "short" else 0.0
        asset = asset_registry.get(symbol)
        theme = asset.asset_class if asset is not None else "other"
        row = by_symbol.setdefault(symbol, {"gross_usd": 0.0, "net_usd": 0.0, "count": 0.0})
        row["gross_usd"] += size
        row["net_usd"] += signed
        row["count"] += 1.0
        theme_row = by_theme.setdefault(theme, {"gross_usd": 0.0, "net_usd": 0.0, "count": 0.0})
        theme_row["gross_usd"] += size
        theme_row["net_usd"] += signed
        theme_row["count"] += 1.0
        gross += size
        net += signed
        impact = impacts.get(symbol) if isinstance(impacts, Mapping) else next((x for x in impacts or () if getattr(x, "symbol", None) == symbol), None)
        direction = _maybe_num(getattr(impact, "direction_score", None)) if impact is not None else None
        confidence = _num(getattr(impact, "confidence", 0.0)) if impact is not None else 0.0
        if direction is not None and confidence >= 0.25 and ((side == "long" and direction < -0.15) or (side == "short" and direction > 0.15)):
            conflicts.append({"symbol": symbol, "side": side, "causal_direction": round(float(direction), 4), "confidence": round(confidence, 4), "reason": "open_position_against_world_thesis"})
    denominator = equity if equity > 0 else None
    symbol_exposure = {
        symbol: {**values, "gross_pct": round(values["gross_usd"] / denominator, 6) if denominator else None, "net_pct": round(values["net_usd"] / denominator, 6) if denominator else None}
        for symbol, values in sorted(by_symbol.items())
    }
    theme_exposure = {
        theme: {**values, "gross_pct": round(values["gross_usd"] / denominator, 6) if denominator else None, "net_pct": round(values["net_usd"] / denominator, 6) if denominator else None}
        for theme, values in sorted(by_theme.items())
    }
    weights = [values["gross_usd"] / gross for values in by_symbol.values()] if gross > 0 else []
    hhi = sum(weight * weight for weight in weights) if weights else None
    warnings: list[str] = []
    if equity <= 0:
        warnings.append("equity_unavailable")
    if not positions:
        warnings.append("no_open_positions")
    if conflicts:
        warnings.append("positions_against_world_thesis")
    if gross > equity > 0:
        warnings.append("gross_exposure_above_equity")
    return PortfolioRiskReport(
        generated_at=generated,
        status="OK" if equity > 0 else "INSUFFICIENT_DATA",
        equity_usd=round(equity, 2), gross_exposure_usd=round(gross, 2), net_exposure_usd=round(net, 2),
        gross_exposure_pct=round(gross / denominator, 6) if denominator else None,
        net_exposure_pct=round(net / denominator, 6) if denominator else None,
        max_symbol_weight=round(max(weights), 6) if weights else None,
        concentration_hhi=round(hhi, 6) if hhi is not None else None,
        symbol_exposure=symbol_exposure, theme_exposure=theme_exposure,
        thesis_conflicts=tuple(conflicts), warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = ["PortfolioRiskReport", "build_portfolio_risk"]
