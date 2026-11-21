"""Options riski (options risk) — yalnızca KISITLAYICI, per-symbol gate (v2.7 D3).

Options zekâsı (IV / skew / term structure) karar zincirine **yalnızca kripto
sembolleri** (BTCUSD/ETHUSD) için ve **yalnızca kısıtlayıcı** girer. Bu modül:

- ASLA size artırmaz (size_factor ≤ 1.0). CHEAP_VOL bile yalnızca bağlamdır —
  otomatik boost YOK.
- ASLA RiskGate / DQS / KillSwitch / halt gate'lerini gevşetmez/bypass etmez —
  decision engine'de RiskGate hard gate'lerinden SONRA, yalnızca küçültücü
  olarak uygulanır (bu modül yalnızca RiskGate açıkken çalışır).
- Yalnızca `verified=True` + `status="OK"` snapshot'ları sayar (fixture/test
  verisi karar zincirine girmez; yalnızca dashboard bağlamı).
- Skew GERÇEK 25Δ greeks DEĞİLDİR (`is_proxy`) — moneyness tabanlı vekil.

Taksonomi (yalnızca kısıtlayıcı):
  NONE                  → etki yok (boost yok)
  WATCH                 → bağlam uyarısı (size değişmez)
  CAUTION               → size ×0.5
  NO_POSITION_INCREASE  → yeni pozisyon açılışı durur (block)

Rejim → risk (yön farkındalıklı):
  PUT_SKEW_STRESS     + open_long  → CAUTION (downside korku; long size reduce)
  CALL_SKEW_EUPHORIA  + open_long  → CAUTION (öfori; long chase cezalandırılır)
  TERM_STRESS                      → NO_POSITION_INCREASE (yakın vade stresi; yön bağımsız)
  RICH_VOL                         → CAUTION (pahalı vol / risk primi; yön bağımsız)
  CHEAP_VOL                        → WATCH (yalnızca bağlam; boost yok)
  NORMAL                           → NONE

Timeframe ağırlığı: options daha çok 4h/1d/1w bağlamıdır → bu TF'lerde tam etki;
15m/1h düşük ağırlık (yalnızca düşük-ağırlıklı uyarı). Düşük ağırlıkta
NO_POSITION_INCREASE block'a dönmez, CAUTION'a yumuşar.

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem + kısıtlama.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from packages.data.types import OptionsSnapshot
from packages.risk import restrictive

OptionsRiskLevel = Literal["NONE", "WATCH", "CAUTION", "NO_POSITION_INCREASE"]

_LEVEL_RANK = restrictive.LEVEL_RANK
_LEVEL_SIZE_FACTOR = restrictive.LEVEL_SIZE_FACTOR



@dataclass
class OptionsVerdict:
    level: OptionsRiskLevel = "NONE"
    size_factor: float = 1.0      # ≤ 1.0 — asla artırmaz
    block: bool = False           # True → yeni pozisyon açılışı durur
    reason: str = "Options stres riski yok."
    regime: str = "NORMAL"
    evidence: list[str] = field(default_factory=list)


def timeframe_weight(timeframe: str) -> float:
    return restrictive.timeframe_weight("options", timeframe)


def assess(
    opt: OptionsSnapshot | None,
    candidate_action: str,
) -> OptionsVerdict:
    """Tek sembolün options snapshot'ından kısıtlayıcı verdict.

    `candidate_action` ∈ {open_long, open_short, hold, blocked}. PUT_SKEW_STRESS
    ve CALL_SKEW_EUPHORIA yalnızca **long açılışını** cezalandırır (downside
    korku / öfori long chase); short/contrarian açılış yalnızca bağlamdır.
    TERM_STRESS ve RICH_VOL yön bağımsızdır.
    """
    # Yalnızca gerçek + sağlıklı veri karar zincirine girer.
    if opt is None or not opt.verified or opt.status != "OK":
        return OptionsVerdict(reason="Options verisi yok/doğrulanmamış (bağlam dışı).")

    regime = opt.regime
    is_long = candidate_action == "open_long"

    if regime == "TERM_STRESS":
        level: OptionsRiskLevel = "NO_POSITION_INCREASE"
        reason = "Term structure stresi (backwardation): yakın vade IV uzun vadeyi aşıyor → yeni pozisyon durdu."
    elif regime == "RICH_VOL":
        level = "CAUTION"
        reason = "Pahalı vol (IV ≫ realized): risk primi yüksek → size ×0.5."
    elif regime == "PUT_SKEW_STRESS":
        if is_long:
            level = "CAUTION"
            reason = "Put skew stresi (downside korku) + long aday → size ×0.5."
        else:
            level = "WATCH"
            reason = "Put skew stresi (downside korku): bağlam uyarısı."
    elif regime == "CALL_SKEW_EUPHORIA":
        if is_long:
            level = "CAUTION"
            reason = "Call skew öforisi + long chase → size ×0.5."
        else:
            level = "WATCH"
            reason = "Call skew öforisi: bağlam uyarısı."
    elif regime == "CHEAP_VOL":
        level = "WATCH"
        reason = "Ucuz vol (IV < realized): yalnızca bağlam — otomatik boost YOK."
    else:  # NORMAL
        return OptionsVerdict(
            regime=regime,
            reason="Options rejimi NORMAL (boost yok).",
            evidence=list(opt.evidence[:2]),
        )

    evidence: list[str] = []
    if opt.atm_iv is not None:
        evidence.append(f"ATM IV {opt.atm_iv * 100:.1f}% (proxy skew)")
    if opt.skew_25d is not None:
        evidence.append(f"25Δ skew proxy {opt.skew_25d * 100:+.1f} vol-pt")
    if opt.iv_rv_spread is not None:
        evidence.append(f"IV−RV {opt.iv_rv_spread * 100:+.1f} vol-pt")
    if opt.term_slope is not None:
        evidence.append(f"term slope {opt.term_slope * 100:+.1f} vol-pt")
    if is_long and regime in ("PUT_SKEW_STRESS", "CALL_SKEW_EUPHORIA"):
        evidence.append("long aday: skew stresiyle aynı yön → cezalandırıldı")

    return OptionsVerdict(
        level=level,
        size_factor=_LEVEL_SIZE_FACTOR[level],
        block=(level == "NO_POSITION_INCREASE"),
        reason=reason,
        regime=regime,
        evidence=evidence,
    )


def apply_timeframe(verdict: OptionsVerdict, weight: float) -> OptionsVerdict:
    """Timeframe ağırlığını uygula. weight=1.0 tam etki; 0.0 etki yok.

    Düşük ağırlıkta (örn. 15m) NO_POSITION_INCREASE block'a DÖNMEZ — etki
    yumuşatılır (size_factor 1.0'a doğru çekilir). Asla artırmaz.
    """
    return restrictive.apply_timeframe(verdict, weight, "Options etkisi bu timeframe'de devre dışı.")
