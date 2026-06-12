"""Türev riski (derivatives risk) — yalnızca KISITLAYICI, per-symbol gate (v2.7 D2).

Crypto derivatives zekâsı (funding / OI / squeeze proxy) karar zincirine
**yalnızca kripto sembolleri** için ve **yalnızca kısıtlayıcı** girer. Bu modül:

- ASLA size artırmaz (size_factor ≤ 1.0).
- ASLA RiskGate / DQS / KillSwitch / halt gate'lerini gevşetmez/bypass etmez —
  decision engine'de RiskGate hard gate'lerinden SONRA, yalnızca küçültücü
  olarak uygulanır.
- Yalnızca `verified=True` + `status="OK"` snapshot'ları sayar (fixture/test
  verisi karar zincirine girmez; yalnızca dashboard bağlamı).
- Squeeze proxy GERÇEK liquidation DEĞİLDİR (`is_proxy`) — yalnızca vekil sinyal.

Taksonomi (yalnızca kısıtlayıcı):
  NONE                  → etki yok (boost yok)
  WATCH                 → bağlam uyarısı (size değişmez)
  CAUTION               → size ×0.5
  NO_POSITION_INCREASE  → yeni pozisyon açılışı durur (block)

Timeframe ağırlığı: 15m/1h reaksiyon için derivatives daha önemli → tam etki;
1d düşük ağırlık → block yerine CAUTION; 1w yok (strategic zaten paper açmaz).

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem + kısıtlama.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from packages.data.registry.loader import load_thresholds
from packages.data.types import DerivativesSnapshot

DerivativesRiskLevel = Literal["NONE", "WATCH", "CAUTION", "NO_POSITION_INCREASE"]

_LEVEL_RANK: dict[DerivativesRiskLevel, int] = {
    "NONE": 0,
    "WATCH": 1,
    "CAUTION": 2,
    "NO_POSITION_INCREASE": 3,
}

_LEVEL_SIZE_FACTOR: dict[DerivativesRiskLevel, float] = {
    "NONE": 1.0,
    "WATCH": 1.0,
    "CAUTION": 0.5,
    "NO_POSITION_INCREASE": 0.0,
}

# Bu ağırlığın altındaki timeframe'lerde NO_POSITION_INCREASE block'a dönmez,
# CAUTION'a düşürülür (1d gibi düşük-ağırlık TF'ler hard-block edilmez).
_BLOCK_WEIGHT_MIN = 0.75


@dataclass
class DerivativesVerdict:
    level: DerivativesRiskLevel = "NONE"
    size_factor: float = 1.0      # ≤ 1.0 — asla artırmaz
    block: bool = False           # True → yeni pozisyon açılışı durur
    reason: str = "Türev sıkışma riski yok."
    evidence: list[str] = field(default_factory=list)


def timeframe_weight(timeframe: str) -> float:
    cfg = (load_thresholds().get("derivatives") or {}).get("timeframe_weight") or {}
    try:
        return max(0.0, min(1.0, float(cfg.get(timeframe, 1.0))))
    except (TypeError, ValueError):
        return 1.0


def _squeeze_level_to_risk(level: str) -> DerivativesRiskLevel:
    return {
        "HIGH": "NO_POSITION_INCREASE",
        "ELEVATED": "CAUTION",
        "LOW": "WATCH",
        "NONE": "NONE",
    }.get(level, "NONE")


def assess(
    deriv: DerivativesSnapshot | None,
    candidate_action: str,
) -> DerivativesVerdict:
    """Tek sembolün türev snapshot'ından kısıtlayıcı verdict.

    `candidate_action` ∈ {open_long, open_short, hold, blocked}. Yalnızca
    crowd ile AYNI yönde açılış cezalandırılır (long chase / short chase);
    contrarian açılış yalnızca bağlamdır (boost yok).
    """
    # Yalnızca gerçek + sağlıklı veri karar zincirine girer.
    if deriv is None or not deriv.verified or deriv.status != "OK":
        return DerivativesVerdict(reason="Türev verisi yok/doğrulanmamış (bağlam dışı).")

    # 1) Squeeze proxy seviyesi (yöne bağımsız — her yeni pozisyona uygulanır).
    squeeze_level = _squeeze_level_to_risk(deriv.squeeze_level)

    # 2) Funding-chase (yöne bağımlı): crowd ile aynı yönde açılış cezalandırılır.
    chase_level: DerivativesRiskLevel = "NONE"
    if candidate_action == "open_long" and deriv.funding_bias == "crowded_long":
        chase_level = "CAUTION"
    elif candidate_action == "open_short" and deriv.funding_bias == "crowded_short":
        chase_level = "CAUTION"
    # contrarian (ör. negatif funding + open_long) → NONE: yalnızca bağlam, boost yok.

    # En kısıtlayıcı seviyeyi seç.
    level: DerivativesRiskLevel = max(
        (squeeze_level, chase_level), key=lambda lv: _LEVEL_RANK[lv]
    )
    if level == "NONE":
        return DerivativesVerdict(
            reason="Türev sıkışma riski düşük (boost yok).",
            evidence=list(deriv.evidence[:2]),
        )

    evidence = [
        f"squeeze {deriv.squeeze_level} (proxy {deriv.squeeze_proxy:.0f}/100, gerçek liq değil)",
        f"funding {deriv.funding_bias}"
        + (f" {deriv.funding_rate * 100:.4f}%/8s" if deriv.funding_rate is not None else ""),
    ]
    if chase_level != "NONE":
        side = "long" if candidate_action == "open_long" else "short"
        evidence.append(f"{side} chase: aday yön kalabalıkla aynı → cezalandırıldı")

    reason = {
        "WATCH": f"Türev bağlam uyarısı: squeeze {deriv.squeeze_level}.",
        "CAUTION": f"Türev riski (CAUTION): squeeze/{deriv.funding_bias} → size ×0.5.",
        "NO_POSITION_INCREASE": (
            f"Türev riski yüksek: squeeze {deriv.squeeze_level} → yeni pozisyon durdu."
        ),
    }[level]

    return DerivativesVerdict(
        level=level,
        size_factor=_LEVEL_SIZE_FACTOR[level],
        block=(level == "NO_POSITION_INCREASE"),
        reason=reason,
        evidence=evidence,
    )


def apply_timeframe(verdict: DerivativesVerdict, weight: float) -> DerivativesVerdict:
    """Timeframe ağırlığını uygula. weight=1.0 tam etki; 0.0 etki yok.

    Düşük ağırlıkta (örn. 1d) NO_POSITION_INCREASE block'a DÖNMEZ — etki
    yumuşatılır (size_factor 1.0'a doğru çekilir). Asla artırmaz.
    """
    if verdict.level == "NONE":
        return verdict
    w = max(0.0, min(1.0, weight))
    if w == 0.0:
        return DerivativesVerdict(reason="Türev etkisi bu timeframe'de devre dışı.")
    # size_factor'ı ağırlıkla 1.0'a doğru yumuşat (yalnızca küçültür).
    eff_size = 1.0 - (1.0 - verdict.size_factor) * w
    eff_size = max(0.0, min(1.0, eff_size))
    block = verdict.block and w >= _BLOCK_WEIGHT_MIN
    eff_level = verdict.level
    if verdict.block and not block:
        eff_level = "CAUTION"  # block yumuşatıldı → kısıtlayıcı ama bloklamaz
    return DerivativesVerdict(
        level=eff_level,
        size_factor=eff_size,
        block=block,
        reason=verdict.reason + (f" (tf×{w:g})" if w < 1.0 else ""),
        evidence=list(verdict.evidence),
    )
