"""Türev (derivatives) motoru — deterministik squeeze proxy hesabı (v2.7 D2).

Saf Python, ağ yok. Ham funding rate + open interest değişimi + kısa vadeli
fiyat momentumu + volatiliteden `DerivativesSnapshot` üretir.

`squeeze_proxy` GERÇEK liquidation verisi DEĞİLDİR — açıkça "proxy" etiketli
(0..100) bir vekildir. Kalabalık pozisyonun (aşırı funding) fiyatın crowd'a
karşı hareketi + artan OI + yüksek volatilite ile sıkışma riskini özetler.

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.data.registry.loader import load_thresholds
from packages.data.types import DerivativesSnapshot, FundingBias, SqueezeLevel

# Momentum/volatilite normalizasyon referansları (squeeze bileşenleri 0..1).
# 1h barlardan beslenir; ~%3 ters momentum veya ~%5 ATR/fiyat "tam" sayılır.
_MOMENTUM_REF = 0.03
_VOL_REF = 0.05


@dataclass
class DerivInput:
    """Adaptörden gelen ham türev verisi (provider-bağımsız)."""

    symbol: str
    funding_rate: float | None = None
    open_interest_usd: float | None = None
    oi_change_pct: float | None = None
    price_momentum_pct: float | None = None
    volatility_pct: float | None = None
    source: str = "unknown"
    verified: bool = False
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))


def _config() -> dict:
    cfg = load_thresholds().get("derivatives") or {}
    w = cfg.get("weights") or {}
    return {
        "crowded_long": float(cfg.get("funding_crowded_long", 0.0005)),
        "crowded_short": float(cfg.get("funding_crowded_short", -0.0005)),
        "extreme": float(cfg.get("funding_extreme", 0.0010)),
        "oi_surge_pct": float(cfg.get("oi_surge_pct", 0.05)),
        "squeeze_low": float(cfg.get("squeeze_low", 35)),
        "squeeze_elevated": float(cfg.get("squeeze_elevated", 55)),
        "squeeze_high": float(cfg.get("squeeze_high", 75)),
        "w_funding": float(w.get("funding", 0.35)),
        "w_oi": float(w.get("oi_change", 0.30)),
        "w_momentum": float(w.get("momentum", 0.20)),
        "w_volatility": float(w.get("volatility", 0.15)),
    }


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _funding_bias(funding_rate: float | None, cfg: dict) -> FundingBias:
    if funding_rate is None:
        return "neutral"
    if funding_rate >= cfg["crowded_long"]:
        return "crowded_long"
    if funding_rate <= cfg["crowded_short"]:
        return "crowded_short"
    return "neutral"


def _squeeze_level(proxy: float, cfg: dict) -> SqueezeLevel:
    if proxy >= cfg["squeeze_high"]:
        return "HIGH"
    if proxy >= cfg["squeeze_elevated"]:
        return "ELEVATED"
    if proxy >= cfg["squeeze_low"]:
        return "LOW"
    return "NONE"


def _freshness(age_sec: float, max_age_sec: float) -> str:
    if age_sec <= max_age_sec * 0.34:
        return "FRESH"
    if age_sec <= max_age_sec:
        return "RECENT"
    return "STALE"


def compute(inp: DerivInput, *, now: datetime | None = None) -> DerivativesSnapshot:
    """Ham türev girdisinden squeeze proxy + funding bias üretir.

    Essential alanlar (funding_rate VE open_interest) yoksa → DEGRADED snapshot
    (squeeze NONE, neutral bias) — mock üretilmez, crash olmaz.
    """
    cfg = _config()
    ref = now or datetime.now(UTC)
    age_sec = max(0.0, (ref - inp.ts).total_seconds())
    max_age = float(load_thresholds().get("derivatives", {}).get("max_age_sec", 900))
    freshness = _freshness(age_sec, max_age)

    # Essential veri yoksa → DEGRADED (karar zincirine girmez).
    if inp.funding_rate is None or inp.open_interest_usd is None:
        missing = []
        if inp.funding_rate is None:
            missing.append("funding_rate")
        if inp.open_interest_usd is None:
            missing.append("open_interest")
        return DerivativesSnapshot(
            symbol=inp.symbol,
            funding_rate=inp.funding_rate,
            open_interest_usd=inp.open_interest_usd,
            oi_change_pct=inp.oi_change_pct,
            price_momentum_pct=inp.price_momentum_pct,
            volatility_pct=inp.volatility_pct,
            status="DEGRADED",
            source=inp.source,
            verified=False,
            freshness=freshness,
            dqs=0.0,
            ts=inp.ts,
            evidence=[f"türev verisi eksik: {', '.join(missing)}"],
            error="incomplete derivatives data",
        )

    bias = _funding_bias(inp.funding_rate, cfg)
    funding_ann = round(inp.funding_rate * 3 * 365, 4)

    # ----- squeeze proxy bileşenleri (her biri 0..1) -----
    # 1) funding: |funding| extreme'e ne kadar yakın (kalabalık pozisyon yakıtı).
    funding_c = _clamp01(abs(inp.funding_rate) / cfg["extreme"]) if cfg["extreme"] > 0 else 0.0
    # 2) OI artışı: yükselen OI = biriken kaldıraç.
    oi = inp.oi_change_pct or 0.0
    oi_c = _clamp01(max(0.0, oi) / cfg["oi_surge_pct"]) if cfg["oi_surge_pct"] > 0 else 0.0
    # 3) momentum: fiyatın crowd'a KARŞI hareketi (long crowd + düşüş = sıkışma).
    mom = inp.price_momentum_pct or 0.0
    crowd_dir = 1.0 if bias == "crowded_long" else -1.0 if bias == "crowded_short" else 0.0
    adverse = -crowd_dir * mom  # crowd'a karşı pozitif
    mom_c = _clamp01(max(0.0, adverse) / _MOMENTUM_REF)
    # 4) volatilite: yüksek vol = daha geniş sıkışma potansiyeli.
    vol = inp.volatility_pct or 0.0
    vol_c = _clamp01(vol / _VOL_REF)

    proxy = 100.0 * (
        cfg["w_funding"] * funding_c
        + cfg["w_oi"] * oi_c
        + cfg["w_momentum"] * mom_c
        + cfg["w_volatility"] * vol_c
    )
    proxy = round(max(0.0, min(100.0, proxy)), 1)
    level = _squeeze_level(proxy, cfg)

    # DQS: tazelik + bileşen tamlığı (momentum/vol opsiyonel).
    completeness = 1.0
    if inp.oi_change_pct is None:
        completeness -= 0.25
    if inp.price_momentum_pct is None:
        completeness -= 0.15
    if inp.volatility_pct is None:
        completeness -= 0.10
    fresh_factor = {"FRESH": 1.0, "RECENT": 0.7, "STALE": 0.3}[freshness]
    dqs = round(100.0 * max(0.0, completeness) * fresh_factor, 1)

    evidence = [
        f"funding {inp.funding_rate * 100:.4f}%/8s ({bias}) · yıllık ≈ {funding_ann * 100:.1f}%",
        f"OI ${inp.open_interest_usd:,.0f}"
        + (f" · Δ {oi * 100:+.1f}%" if inp.oi_change_pct is not None else ""),
        f"squeeze proxy {proxy:.0f}/100 → {level} (PROXY — gerçek liquidation değil)",
    ]

    return DerivativesSnapshot(
        symbol=inp.symbol,
        funding_rate=round(inp.funding_rate, 6),
        funding_annualized=funding_ann,
        open_interest_usd=round(inp.open_interest_usd, 2),
        oi_change_pct=round(oi, 4) if inp.oi_change_pct is not None else None,
        price_momentum_pct=round(mom, 4) if inp.price_momentum_pct is not None else None,
        volatility_pct=round(vol, 4) if inp.volatility_pct is not None else None,
        squeeze_proxy=proxy,
        squeeze_level=level,
        funding_bias=bias,
        is_proxy=True,
        status="OK",
        source=inp.source,
        verified=inp.verified,
        freshness=freshness,  # type: ignore[arg-type]
        dqs=dqs,
        ts=inp.ts,
        evidence=evidence,
    )
