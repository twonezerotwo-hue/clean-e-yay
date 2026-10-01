"""Deterministic, evidence-calibrated price bands.

This is deliberately a small observation layer.  A band is only emitted when
there is a positive current price and an observed volatility input (ATR or
realized volatility).  Missing inputs remain explicit; no neutral volatility
or fabricated target is substituted.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

_HORIZON_DAYS: dict[str, float] = {
    "1h": 1.0 / 24.0,
    "4h": 4.0 / 24.0,
    "1d": 1.0,
    "1w": 5.0,
}
_Z = {"p10": -1.2816, "p25": -0.6745, "p50": 0.0, "p75": 0.6745, "p90": 1.2816}
_TF_FOR_HORIZON = {"1h": "1h", "4h": "4h", "1d": "1d", "1w": "1d"}


@dataclass(frozen=True)
class ForecastBand:
    """One horizon's approximate distribution, never a trade instruction."""

    symbol: str
    horizon: str
    as_of: str
    current_price: float | None
    point_estimate: float | None
    p10: float | None
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None
    directional_bias: str
    confidence: float
    volatility_abs: float | None
    volatility_source: str
    method: str = "normal_approximation_shadow_v1"
    available: bool = True
    missing_inputs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _read_tf(technicals: Mapping[str, Any] | None, symbol: str, timeframe: str) -> Any:
    if not isinstance(technicals, Mapping):
        return None
    row = technicals.get(symbol)
    if isinstance(row, Mapping):
        return row.get(timeframe) or row.get(timeframe.casefold())
    return row if timeframe == "1d" else None


def _atr_from(technical: Any) -> float | None:
    if technical is None:
        return None
    levels = getattr(technical, "key_levels", None)
    atr = _number(getattr(levels, "atr", None))
    if atr is not None and atr > 0:
        return atr
    # Legacy TechnicalSnapshot carries ATR directly.
    atr = _number(getattr(technical, "atr", None))
    return atr if atr is not None and atr > 0 else None


def _atr_percent_from(technical: Any, price: float) -> float | None:
    if technical is None:
        return None
    levels = getattr(technical, "key_levels", None)
    pct = _number(getattr(levels, "atr_percent", None))
    if pct is not None and pct > 0:
        return price * pct / 100.0
    return None


def _realized_vol_from(volatility: Mapping[str, Any] | None, symbol: str, timeframe: str) -> float | None:
    if not isinstance(volatility, Mapping):
        return None
    by_tf = volatility.get(symbol)
    if not isinstance(by_tf, Mapping):
        return None
    item = by_tf.get(timeframe) or by_tf.get(timeframe.casefold())
    realized = _number(getattr(item, "realized_vol", None))
    if realized is None and isinstance(item, Mapping):
        realized = _number(item.get("realized_vol"))
    return realized if realized is not None and realized > 0 else None


def _price(item: Any) -> tuple[float | None, str]:
    value = _number(getattr(item, "price", None))
    if value is None and isinstance(item, Mapping):
        value = _number(item.get("price"))
    if value is None or value <= 0:
        return None, "unavailable"
    status = str(getattr(item, "status", None) or (item.get("status") if isinstance(item, Mapping) else "OK")).upper()
    if status in {"DATA_UNAVAILABLE", "MOCK"}:
        return None, status.lower()
    return value, status.lower()


def _impact_for(impacts: Mapping[str, Any] | Iterable[Any], symbol: str) -> Any:
    if isinstance(impacts, Mapping):
        return impacts.get(symbol)
    for item in impacts or ():
        if getattr(item, "symbol", None) == symbol or (isinstance(item, Mapping) and item.get("symbol") == symbol):
            return item
    return None


def _impact_values(impact: Any) -> tuple[float | None, float]:
    if impact is None:
        return None, 0.0
    direction = _number(getattr(impact, "direction_score", None))
    confidence = _number(getattr(impact, "confidence", None))
    if isinstance(impact, Mapping):
        direction = _number(impact.get("direction_score"))
        confidence = _number(impact.get("confidence"))
    return (max(-1.0, min(1.0, direction)) if direction is not None else None), _clamp(confidence or 0.0)


def _unavailable(
    symbol: str,
    horizon: str,
    now: str,
    missing: list[str],
    warnings: list[str],
    current: float | None = None,
) -> ForecastBand:
    return ForecastBand(
        symbol=symbol, horizon=horizon, as_of=now, current_price=current,
        point_estimate=None, p10=None, p25=None, p50=None, p75=None, p90=None,
        directional_bias="UNKNOWN", confidence=0.0, volatility_abs=None,
        volatility_source="UNAVAILABLE", available=False,
        missing_inputs=tuple(dict.fromkeys(missing)), warnings=tuple(dict.fromkeys(warnings)),
    )


def build_forecasts(
    symbols: Iterable[str],
    *,
    prices: Mapping[str, Any] | Iterable[Any] | None = None,
    impacts: Mapping[str, Any] | Iterable[Any] = (),
    technicals: Mapping[str, Any] | None = None,
    volatility: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> tuple[ForecastBand, ...]:
    """Build bands for every requested symbol and horizon.

    The function is deterministic for a fixed input snapshot.  It uses a
    directional drift only as a small, confidence-weighted shadow component;
    uncertainty comes from observed ATR or realized volatility.  No band is
    returned as an actionable order or guaranteed target.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    price_map: dict[str, Any] = {}
    if isinstance(prices, Mapping):
        price_map = dict(prices)
    else:
        for item in prices or ():
            key = getattr(item, "symbol", None) or (item.get("symbol") if isinstance(item, Mapping) else None)
            if key:
                price_map[str(key)] = item
    output: list[ForecastBand] = []
    for symbol in symbols:
        symbol = str(symbol).upper()
        current, price_status = _price(price_map.get(symbol))
        impact = _impact_for(impacts, symbol)
        direction, impact_confidence = _impact_values(impact)
        for horizon, days in _HORIZON_DAYS.items():
            missing: list[str] = []
            warnings: list[str] = []
            if current is None:
                missing.append("verified_current_price")
                if price_status != "unavailable":
                    warnings.append(f"price_status:{price_status}")
                output.append(_unavailable(symbol, horizon, moment, missing, warnings, current))
                continue
            tf = _TF_FOR_HORIZON[horizon]
            technical = _read_tf(technicals, symbol, tf)
            atr = _atr_from(technical) or _atr_percent_from(technical, current)
            rv = _realized_vol_from(volatility, symbol, tf)
            daily_sigma: float | None = None
            source = "UNAVAILABLE"
            if atr is not None:
                # ATR is a one-bar absolute range.  Scale by the requested
                # horizon only; no annualisation assumption is introduced.
                bar_days = {"1h": 1 / 24, "4h": 4 / 24, "1d": 1.0}.get(tf, 1.0)
                daily_sigma = atr * math.sqrt(max(days / bar_days, 1e-9))
                source = f"ATR:{tf}"
            elif rv is not None:
                daily_sigma = current * rv / math.sqrt(252.0) * math.sqrt(max(days, 1e-9))
                source = f"REALIZED_VOL:{tf}"
            if daily_sigma is None or daily_sigma <= 0 or not math.isfinite(daily_sigma):
                missing.append("observed_volatility")
                output.append(_unavailable(symbol, horizon, moment, missing, warnings, current))
                continue
            if direction is None:
                warnings.append("causal_direction_unavailable")
                drift = 0.0
                bias = "UNKNOWN"
                confidence = 0.0
            else:
                drift = direction * impact_confidence * daily_sigma * 0.35
                bias = "BULLISH" if direction > 0.05 else "BEARISH" if direction < -0.05 else "NEUTRAL"
                confidence = _clamp(impact_confidence)
            point = max(current * 1e-9, current + drift)
            values = {name: max(current * 1e-9, point + z * daily_sigma) for name, z in _Z.items()}
            output.append(ForecastBand(
                symbol=symbol, horizon=horizon, as_of=moment,
                current_price=round(current, 10), point_estimate=round(point, 10),
                p10=round(values["p10"], 10), p25=round(values["p25"], 10),
                p50=round(values["p50"], 10), p75=round(values["p75"], 10),
                p90=round(values["p90"], 10), directional_bias=bias,
                confidence=round(confidence, 4), volatility_abs=round(daily_sigma, 10),
                volatility_source=source, warnings=tuple(dict.fromkeys(warnings)),
            ))
    return tuple(output)


__all__ = ["ForecastBand", "build_forecasts"]
