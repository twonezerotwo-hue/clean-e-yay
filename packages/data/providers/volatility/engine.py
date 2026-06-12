"""Realized volatility motoru — deterministik, saf Python (v2.7 D4).

Ağ yok. Mevcut OHLCV barlarından log-getiri tabanlı annualize realized
volatility, rolling pencereler (short/medium/long), volatilite z-score'u,
rejim (LOW/NORMAL/ELEVATED/EXTREME) ve squeeze/expansion/shock bağlam
bayrağı üretir.

Bar yetersizse → `status="DEGRADED"`, alanlar None (mock üretilmez, crash yok).

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise

from packages.data.registry.loader import load_thresholds
from packages.data.types import OHLCVBar, VolatilityRegime, VolatilitySnapshot, VolState

# TF başına yıllık bar sayısı (annualizasyon: rv = stdev × sqrt(bars_per_year)).
_BARS_PER_YEAR: dict[str, float] = {
    "15m": 4 * 24 * 365,
    "1h": 24 * 365,
    "4h": 6 * 365,
    "1d": 365.0,
    "1w": 52.0,
}


@dataclass
class VolInput:
    """Tek (symbol, timeframe) için ham OHLCV barları (provider-bağımsız)."""

    symbol: str
    timeframe: str
    bars: list[OHLCVBar] = field(default_factory=list)
    source: str = "unknown"
    verified: bool = False


def _config() -> dict:
    cfg = load_thresholds().get("volatility") or {}
    w = cfg.get("windows") or {}
    rz = cfg.get("regime_z") or {}
    return {
        "short": int(w.get("short", 10)),
        "medium": int(w.get("medium", 20)),
        "long": int(w.get("long", 60)),
        "zscore_lookback": int(cfg.get("zscore_lookback", 60)),
        "min_samples": int(cfg.get("min_samples", 20)),
        "z_low": float(rz.get("low", -1.0)),
        "z_elevated": float(rz.get("elevated", 1.0)),
        "z_extreme": float(rz.get("extreme", 2.0)),
        "squeeze_ratio": float(cfg.get("squeeze_ratio", 0.70)),
        "expansion_ratio": float(cfg.get("expansion_ratio", 1.30)),
        "shock_ratio": float(cfg.get("shock_ratio", 2.00)),
        "shock_sigma": float(cfg.get("shock_sigma", 3.0)),
        "max_age": float((cfg.get("max_age_sec") or {}).get("1d", 172800)),
    }


def _max_age_for(timeframe: str) -> float:
    cfg = (load_thresholds().get("volatility") or {}).get("max_age_sec") or {}
    try:
        return float(cfg.get(timeframe, cfg.get("1d", 172800)))
    except (TypeError, ValueError):
        return 172800.0


def _stdev(values: list[float]) -> float:
    """Örneklem (n-1) standart sapması. n < 2 → 0.0."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(var)


def _log_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for prev, cur in pairwise(closes):
        if prev > 0 and cur > 0:
            out.append(math.log(cur / prev))
    return out


def _annualized(returns_window: list[float], bars_per_year: float) -> float:
    return _stdev(returns_window) * math.sqrt(bars_per_year)


def _freshness(age_sec: float, max_age_sec: float) -> str:
    if age_sec <= max_age_sec * 0.34:
        return "FRESH"
    if age_sec <= max_age_sec:
        return "RECENT"
    return "STALE"


def _regime(z: float, cfg: dict) -> VolatilityRegime:
    if z <= cfg["z_low"]:
        return "LOW"
    if z < cfg["z_elevated"]:
        return "NORMAL"
    if z < cfg["z_extreme"]:
        return "ELEVATED"
    return "EXTREME"


def _vol_state(
    *,
    rv_short: float,
    rv_long: float,
    last_return: float,
    stdev_medium: float,
    cfg: dict,
) -> VolState:
    """squeeze / expansion / shock bağlam bayrağı (öncelik: shock > exp > squeeze)."""
    ratio = rv_short / rv_long if rv_long > 0 else 1.0
    shock_by_jump = stdev_medium > 0 and abs(last_return) >= cfg["shock_sigma"] * stdev_medium
    if ratio >= cfg["shock_ratio"] or shock_by_jump:
        return "shock"
    if ratio >= cfg["expansion_ratio"]:
        return "expansion"
    if ratio <= cfg["squeeze_ratio"]:
        return "squeeze"
    return "normal"


def _degraded(inp: VolInput, *, error: str, bars_used: int, note: str) -> VolatilitySnapshot:
    return VolatilitySnapshot(
        symbol=inp.symbol,
        timeframe=inp.timeframe,  # type: ignore[arg-type]
        status="DEGRADED",
        source=inp.source,
        verified=False,
        dqs=0.0,
        bars_used=bars_used,
        evidence=[note],
        error=error,
    )


def compute(inp: VolInput, *, now: datetime | None = None) -> VolatilitySnapshot:
    """Ham OHLCV barlarından realized vol + rejim + vol_state üretir.

    Bar yetersizse (`insufficient_bars`) → DEGRADED snapshot (karar dışı).
    """
    cfg = _config()
    short, medium, long_w = cfg["short"], cfg["medium"], cfg["long"]
    bars = inp.bars or []
    closes = [b.close for b in bars if b.close and b.close > 0]
    returns = _log_returns(closes)

    # z-skoru dağılımı için en az short + min_samples getiri; ayrıca medium
    # pencere headline realized_vol için gerekli.
    min_returns = max(short + cfg["min_samples"], medium)
    if len(returns) < min_returns:
        return _degraded(
            inp,
            error="insufficient_bars",
            bars_used=len(bars),
            note=(
                f"yetersiz bar: {len(returns)} getiri < {min_returns} "
                "(realized vol + z-skoru için) → DEGRADED"
            ),
        )

    bpy = _BARS_PER_YEAR.get(inp.timeframe, 365.0)
    rv_short = _annualized(returns[-short:], bpy)
    rv_medium = _annualized(returns[-medium:], bpy)
    long_avail = min(long_w, len(returns))
    rv_long = _annualized(returns[-long_avail:], bpy)

    # rv_short rolling serisi → z-skoru (kendi geçmişine göre ne kadar uçta).
    series: list[float] = []
    n_samples = len(returns) - short + 1
    for j in range(max(0, n_samples - cfg["zscore_lookback"]), n_samples):
        series.append(_annualized(returns[j:j + short], bpy))
    s_mean = sum(series) / len(series)
    s_std = _stdev(series)
    z = (rv_short - s_mean) / s_std if s_std > 0 else 0.0
    z = round(z, 3)

    regime = _regime(z, cfg)
    stdev_medium = _stdev(returns[-medium:])
    state = _vol_state(
        rv_short=rv_short,
        rv_long=rv_long,
        last_return=returns[-1],
        stdev_medium=stdev_medium,
        cfg=cfg,
    )

    # Tazelik (son bar yaşı) → DQS bileşeni.
    ref = now or datetime.now(UTC)
    last_ts = bars[-1].ts
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=UTC)
    age_sec = max(0.0, (ref - last_ts).total_seconds())
    freshness = _freshness(age_sec, _max_age_for(inp.timeframe))
    fresh_factor = {"FRESH": 1.0, "RECENT": 0.7, "STALE": 0.3}[freshness]
    # Tamlık: tam long penceresi varsa 1.0, yoksa oransal.
    completeness = min(1.0, len(returns) / float(long_w)) if long_w > 0 else 1.0
    dqs = round(100.0 * completeness * fresh_factor, 1)

    evidence = [
        f"realized vol (annualize) short {rv_short * 100:.1f}% · "
        f"medium {rv_medium * 100:.1f}% · long {rv_long * 100:.1f}%",
        f"z-skoru {z:+.2f} → rejim {regime}",
    ]
    if state != "normal":
        evidence.append(f"vol durumu: {state} (rv_short/rv_long ≈ {rv_short / rv_long:.2f})"
                        if rv_long > 0 else f"vol durumu: {state}")

    return VolatilitySnapshot(
        symbol=inp.symbol,
        timeframe=inp.timeframe,  # type: ignore[arg-type]
        realized_vol=round(rv_medium, 6),
        rv_short=round(rv_short, 6),
        rv_medium=round(rv_medium, 6),
        rv_long=round(rv_long, 6),
        vol_zscore=z,
        regime=regime,
        vol_state=state,
        status="OK",
        source=inp.source,
        verified=inp.verified,
        freshness=freshness,  # type: ignore[arg-type]
        dqs=dqs,
        bars_used=len(bars),
        ts=last_ts,
        evidence=evidence,
    )
