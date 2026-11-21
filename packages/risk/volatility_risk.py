"""Volatilite riski (volatility risk) — yalnızca KISITLAYICI gate (v2.7 D4).

Realized volatility zekâsı (rejim + squeeze/expansion/shock) karar zincirine
**yalnızca kısıtlayıcı** girer. Bu modül:

- ASLA size artırmaz (size_factor ≤ 1.0).
- ASLA RiskGate / DQS / KillSwitch / halt gate'lerini gevşetmez/bypass etmez —
  decision engine'de RiskGate hard gate'lerinden SONRA, yalnızca küçültücü
  olarak uygulanır.
- Yalnızca `verified=True` + `status="OK"` snapshot'ları sayar (fixture/test
  verisi karar zincirine girmez; yalnızca dashboard bağlamı).

Taksonomi (yalnızca kısıtlayıcı):
  NONE                  → etki yok (boost yok)
  WATCH                 → bağlam uyarısı (size değişmez)
  CAUTION               → size ×0.5
  NO_POSITION_INCREASE  → yeni pozisyon açılışı durur (block)

Eşleme:
  EXTREME rejim         → NO_POSITION_INCREASE
  ELEVATED rejim        → CAUTION
  NORMAL rejim          → NONE
  LOW rejim             → WATCH (LOW + squeeze breakout = yalnızca bağlam, boost YOK)
  shock                 → en az CAUTION; rejim ELEVATED/EXTREME ise NO_POSITION_INCREASE
  expansion             → WATCH (genişleyen vol = bağlam)
  squeeze               → WATCH (yalnızca bağlam — asla boost)

Yön bağımsız: yüksek volatilite hem long hem short için risklidir (funding gibi
yön-kovalama yoktur). Timeframe ağırlığı: 15m/1h shock için tam etki; 1d/1w
rejim bağlamı (düşük ağırlık → block CAUTION'a yumuşar; 1w etki yok).

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem + kısıtlama.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from packages.data.types import VolatilitySnapshot
from packages.risk import restrictive

VolatilityRiskLevel = Literal["NONE", "WATCH", "CAUTION", "NO_POSITION_INCREASE"]

_LEVEL_RANK = restrictive.LEVEL_RANK
_LEVEL_SIZE_FACTOR = restrictive.LEVEL_SIZE_FACTOR



@dataclass
class VolatilityVerdict:
    level: VolatilityRiskLevel = "NONE"
    size_factor: float = 1.0      # ≤ 1.0 — asla artırmaz
    block: bool = False           # True → yeni pozisyon açılışı durur
    reason: str = "Volatilite riski düşük."
    evidence: list[str] = field(default_factory=list)


def timeframe_weight(timeframe: str) -> float:
    return restrictive.timeframe_weight("volatility", timeframe)


def _regime_to_risk(regime: str) -> VolatilityRiskLevel:
    return {
        "EXTREME": "NO_POSITION_INCREASE",
        "ELEVATED": "CAUTION",
        "NORMAL": "NONE",
        "LOW": "WATCH",
    }.get(regime, "NONE")


def _state_to_risk(state: str, regime: str) -> VolatilityRiskLevel:
    if state == "shock":
        # 15m/1h'de vol shock daha etkili (timeframe ağırlığı tam tutar);
        # rejim zaten yüksekse shock açılışı durdurur.
        return "NO_POSITION_INCREASE" if regime in ("ELEVATED", "EXTREME") else "CAUTION"
    if state in ("expansion", "squeeze"):
        return "WATCH"  # squeeze breakout dâhil yalnızca bağlam — asla boost
    return "NONE"


def assess(
    vol: VolatilitySnapshot | None,
    candidate_action: str,
) -> VolatilityVerdict:
    """Tek (symbol, timeframe) vol snapshot'ından kısıtlayıcı verdict.

    Yön bağımsızdır (yüksek vol her yönde risklidir). `candidate_action` yalnızca
    bağlam içindir; engine zaten gate'i sadece gerçek açılış adayına uygular.
    """
    # Yalnızca gerçek + sağlıklı veri karar zincirine girer.
    if vol is None or not vol.verified or vol.status != "OK":
        return VolatilityVerdict(reason="Volatilite verisi yok/doğrulanmamış (bağlam dışı).")

    regime_level = _regime_to_risk(vol.regime)
    state_level = _state_to_risk(vol.vol_state, vol.regime)

    level: VolatilityRiskLevel = max(
        (regime_level, state_level), key=lambda lv: _LEVEL_RANK[lv]
    )
    if level == "NONE":
        return VolatilityVerdict(
            reason="Volatilite rejimi normal (boost yok).",
            evidence=list(vol.evidence[:2]),
        )

    evidence = [
        f"rejim {vol.regime}"
        + (f" (z {vol.vol_zscore:+.2f})" if vol.vol_zscore is not None else ""),
    ]
    if vol.vol_state != "normal":
        evidence.append(f"vol durumu: {vol.vol_state}")
    if vol.realized_vol is not None:
        evidence.append(f"realized vol ≈ {vol.realized_vol * 100:.1f}% (annualize)")

    reason = {
        "WATCH": f"Volatilite bağlam uyarısı: rejim {vol.regime}"
        + (f" · {vol.vol_state}" if vol.vol_state != "normal" else "") + ".",
        "CAUTION": (
            f"Volatilite riski (CAUTION): rejim {vol.regime}"
            + (f" / {vol.vol_state}" if vol.vol_state != "normal" else "")
            + " → size ×0.5."
        ),
        "NO_POSITION_INCREASE": (
            f"Volatilite riski yüksek: rejim {vol.regime}"
            + (f" / {vol.vol_state}" if vol.vol_state != "normal" else "")
            + " → yeni pozisyon durdu."
        ),
    }[level]

    return VolatilityVerdict(
        level=level,
        size_factor=_LEVEL_SIZE_FACTOR[level],
        block=(level == "NO_POSITION_INCREASE"),
        reason=reason,
        evidence=evidence,
    )


def apply_timeframe(verdict: VolatilityVerdict, weight: float) -> VolatilityVerdict:
    """Timeframe ağırlığını uygula. weight=1.0 tam etki; 0.0 etki yok.

    Düşük ağırlıkta (örn. 1d) NO_POSITION_INCREASE block'a DÖNMEZ — etki
    yumuşatılır (size_factor 1.0'a doğru çekilir, rejim bağlamı kalır).
    Asla artırmaz.
    """
    return restrictive.apply_timeframe(verdict, weight, "Volatilite etkisi bu timeframe'de devre dışı.")
