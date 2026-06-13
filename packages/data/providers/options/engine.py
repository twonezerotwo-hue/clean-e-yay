"""Options motoru — deterministik IV / skew / term structure hesabı (v2.7 D3).

Saf Python, ağ yok. Ham options chain (strike × expiry × call/put × mark_iv ×
open_interest) + opsiyonel realized vol'den `OptionsSnapshot` üretir:

- ATM implied volatility (ön vade, underlying'e en yakın strike).
- 25Δ skew / risk-reversal **proxy** (moneyness tabanlı; gerçek greeks değil):
  ön vadede OTM call IV − OTM put IV (negatif = put skew / korku).
- put/call open-interest oranı.
- term structure (front / next / long vade ATM IV) + slope (long − front).
- realized-vs-implied spread (atm_iv − realized_vol).
- options stress rejimi (NORMAL / RICH_VOL / CHEAP_VOL / PUT_SKEW_STRESS /
  CALL_SKEW_EUPHORIA / TERM_STRESS).

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from packages.data.registry.loader import load_thresholds
from packages.data.types import OptionsRegime, OptionsSnapshot

# OTM hedef moneyness — 25Δ bölgesine yaklaşık (gerçek greeks yok → proxy).
_OTM_CALL_MONEYNESS = 1.10
_OTM_PUT_MONEYNESS = 0.90


@dataclass
class OptionQuote:
    """Tek opsiyon kotasyonu (provider-bağımsız ham veri)."""

    expiry_ts: datetime
    strike: float
    option_type: Literal["call", "put"]
    mark_iv: float                 # annualize ondalık (0.55 = %55)
    open_interest: float = 0.0
    expiry_label: str = ""


@dataclass
class OptionsInput:
    symbol: str
    underlying_price: float | None
    quotes: list[OptionQuote] = field(default_factory=list)
    realized_vol: float | None = None     # D4 realized vol (annualize ondalık)
    source: str = "unknown"
    verified: bool = False
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))


def _config() -> dict:
    cfg = load_thresholds().get("options") or {}
    return {
        "rich_vol_spread": float(cfg.get("rich_vol_spread", 0.10)),
        "cheap_vol_spread": float(cfg.get("cheap_vol_spread", -0.05)),
        "put_skew_stress": float(cfg.get("put_skew_stress", -0.03)),
        "call_skew_euphoria": float(cfg.get("call_skew_euphoria", 0.03)),
        "term_stress_slope": float(cfg.get("term_stress_slope", -0.02)),
        "max_age_sec": float(cfg.get("max_age_sec", 900)),
    }


def _freshness(age_sec: float, max_age_sec: float) -> str:
    if age_sec <= max_age_sec * 0.34:
        return "FRESH"
    if age_sec <= max_age_sec:
        return "RECENT"
    return "STALE"


def _atm_iv(quotes: list[OptionQuote], underlying: float) -> float | None:
    """Underlying'e en yakın strike'ın call+put IV ortalaması."""
    if not quotes or underlying <= 0:
        return None
    nearest = min(quotes, key=lambda q: abs(q.strike - underlying))
    band = nearest.strike
    near = [q for q in quotes if q.strike == band]
    ivs = [q.mark_iv for q in near if q.mark_iv is not None]
    return sum(ivs) / len(ivs) if ivs else None


def _otm_iv(
    quotes: list[OptionQuote],
    option_type: str,
    underlying: float,
    target_moneyness: float,
) -> float | None:
    """Hedef moneyness'a en yakın OTM call/put IV'si (25Δ proxy)."""
    target = underlying * target_moneyness
    cands = [q for q in quotes if q.option_type == option_type and q.mark_iv is not None]
    if option_type == "call":
        cands = [q for q in cands if q.strike >= underlying] or cands
    else:
        cands = [q for q in cands if q.strike <= underlying] or cands
    if not cands:
        return None
    pick = min(cands, key=lambda q: abs(q.strike - target))
    return pick.mark_iv


def _classify(
    *,
    iv_rv_spread: float | None,
    skew_25d: float | None,
    term_slope: float | None,
    cfg: dict,
) -> OptionsRegime:
    """Tek stress rejimi (öncelik: en kısıtlayıcı/akut sinyal kazanır)."""
    if term_slope is not None and term_slope <= cfg["term_stress_slope"]:
        return "TERM_STRESS"
    if skew_25d is not None and skew_25d <= cfg["put_skew_stress"]:
        return "PUT_SKEW_STRESS"
    if skew_25d is not None and skew_25d >= cfg["call_skew_euphoria"]:
        return "CALL_SKEW_EUPHORIA"
    if iv_rv_spread is not None and iv_rv_spread >= cfg["rich_vol_spread"]:
        return "RICH_VOL"
    if iv_rv_spread is not None and iv_rv_spread <= cfg["cheap_vol_spread"]:
        return "CHEAP_VOL"
    return "NORMAL"


def compute(inp: OptionsInput, *, now: datetime | None = None) -> OptionsSnapshot:
    """Ham options chain'den IV/skew/term structure + stress rejimi üretir.

    Chain boş / underlying yok → UNAVAILABLE. ATM IV hesaplanamıyorsa → DEGRADED.
    Mock üretmez, crash etmez.
    """
    cfg = _config()
    ref = now or datetime.now(UTC)
    age_sec = max(0.0, (ref - inp.ts).total_seconds())
    freshness = _freshness(age_sec, cfg["max_age_sec"])

    if inp.underlying_price is None or inp.underlying_price <= 0 or not inp.quotes:
        return OptionsSnapshot(
            symbol=inp.symbol,
            underlying_price=inp.underlying_price,
            status="UNAVAILABLE",
            source=inp.source,
            verified=False,
            freshness=freshness,  # type: ignore[arg-type]
            ts=inp.ts,
            evidence=["options chain yok / underlying eksik → UNAVAILABLE (mock yok)"],
            error="no options chain",
        )

    underlying = inp.underlying_price
    # Vadeleri grupla + sırala (yakından uzağa).
    by_expiry: dict[datetime, list[OptionQuote]] = {}
    for q in inp.quotes:
        by_expiry.setdefault(q.expiry_ts, []).append(q)
    expiries = sorted(by_expiry.keys())
    labels = {ts: (by_expiry[ts][0].expiry_label or ts.date().isoformat()) for ts in expiries}

    front_ts = expiries[0]
    front_quotes = by_expiry[front_ts]
    atm_iv = _atm_iv(front_quotes, underlying)
    if atm_iv is None:
        return OptionsSnapshot(
            symbol=inp.symbol,
            underlying_price=underlying,
            status="DEGRADED",
            source=inp.source,
            verified=False,
            freshness=freshness,  # type: ignore[arg-type]
            ts=inp.ts,
            contracts_used=len(inp.quotes),
            evidence=["ATM IV hesaplanamadı (strike kapsamı yetersiz) → DEGRADED"],
            error="atm iv unavailable",
        )

    # 25Δ skew proxy (ön vade): risk reversal = OTM call IV − OTM put IV.
    call_iv = _otm_iv(front_quotes, "call", underlying, _OTM_CALL_MONEYNESS)
    put_iv = _otm_iv(front_quotes, "put", underlying, _OTM_PUT_MONEYNESS)
    skew_25d = (
        round(call_iv - put_iv, 4) if (call_iv is not None and put_iv is not None) else None
    )

    # put/call open-interest oranı (tüm chain).
    put_oi = sum(q.open_interest for q in inp.quotes if q.option_type == "put")
    call_oi = sum(q.open_interest for q in inp.quotes if q.option_type == "call")
    pc_ratio = round(put_oi / call_oi, 4) if call_oi > 0 else None

    # Term structure: front / next / long vade ATM IV.
    term_front_iv = atm_iv
    term_next_iv = _atm_iv(by_expiry[expiries[1]], underlying) if len(expiries) >= 2 else None
    term_long_iv = _atm_iv(by_expiry[expiries[-1]], underlying) if len(expiries) >= 2 else None
    term_slope = (
        round(term_long_iv - term_front_iv, 4)
        if (term_long_iv is not None and term_front_iv is not None)
        else None
    )

    iv_rv_spread = (
        round(atm_iv - inp.realized_vol, 4) if inp.realized_vol is not None else None
    )

    regime = _classify(
        iv_rv_spread=iv_rv_spread, skew_25d=skew_25d, term_slope=term_slope, cfg=cfg
    )

    # DQS: tazelik + bileşen tamlığı.
    completeness = 1.0
    if skew_25d is None:
        completeness -= 0.20
    if pc_ratio is None:
        completeness -= 0.15
    if term_slope is None:
        completeness -= 0.15
    if iv_rv_spread is None:
        completeness -= 0.10
    fresh_factor = {"FRESH": 1.0, "RECENT": 0.7, "STALE": 0.3}[freshness]
    dqs = round(100.0 * max(0.0, completeness) * fresh_factor, 1)

    evidence = [
        f"ATM IV ≈ {atm_iv * 100:.1f}% (ön vade {labels[front_ts]})",
    ]
    if skew_25d is not None:
        evidence.append(
            f"25Δ skew proxy {skew_25d * 100:+.1f} vol-pt "
            f"({'put skew' if skew_25d < 0 else 'call skew' if skew_25d > 0 else 'düz'})"
        )
    if iv_rv_spread is not None:
        evidence.append(
            f"IV−RV spread {iv_rv_spread * 100:+.1f} vol-pt "
            f"(realized ≈ {inp.realized_vol * 100:.1f}%)"
        )
    if term_slope is not None:
        evidence.append(
            f"term slope {term_slope * 100:+.1f} vol-pt "
            f"({'backwardation' if term_slope < 0 else 'contango'})"
        )
    if pc_ratio is not None:
        evidence.append(f"put/call OI {pc_ratio:.2f}")
    evidence.append(f"rejim: {regime}")

    return OptionsSnapshot(
        symbol=inp.symbol,
        underlying_price=round(underlying, 2),
        atm_iv=round(atm_iv, 4),
        realized_vol=round(inp.realized_vol, 4) if inp.realized_vol is not None else None,
        iv_rv_spread=iv_rv_spread,
        skew_25d=skew_25d,
        put_call_oi_ratio=pc_ratio,
        term_front_iv=round(term_front_iv, 4),
        term_next_iv=round(term_next_iv, 4) if term_next_iv is not None else None,
        term_long_iv=round(term_long_iv, 4) if term_long_iv is not None else None,
        term_slope=term_slope,
        front_expiry=labels[front_ts],
        next_expiry=labels[expiries[1]] if len(expiries) >= 2 else None,
        long_expiry=labels[expiries[-1]] if len(expiries) >= 2 else None,
        contracts_used=len(inp.quotes),
        regime=regime,
        is_proxy=True,
        status="OK",
        source=inp.source,
        verified=inp.verified,
        freshness=freshness,  # type: ignore[arg-type]
        dqs=dqs,
        ts=inp.ts,
        evidence=evidence,
    )
