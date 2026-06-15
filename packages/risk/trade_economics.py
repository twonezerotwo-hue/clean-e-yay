"""Per-trade economics gate (step 6) — cost + risk:reward, RiskGate-side.

Eklemeli (additive) ve YALNIZCA kısıtlayıcı: önerilen bir girişin maliyet sonrası
net edge'i (`min_net_edge_bps`) veya risk:reward'ı (`min_rr`) yetersizse girişi
BLOCK eder. ASLA giriş üretmez, ASLA size artırmaz — RiskGate tek nihai otoritedir
(bkz. `packages/risk/engine.py`). Saf/deterministik.

Tasarım `engine.py`'daki `RiskDecision` deseniyle aynı: internal dataclass'lar
(contract/openapi yüzeyi yok; guard `^class RiskDecision` / `^RiskAction = Literal`
tetiklenmez). Eksik/geçersiz seviye = diagnostic BLOCK, asla uydurma `allow`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packages.data.registry.loader import load_thresholds

BPS = 10_000.0


@dataclass(frozen=True)
class TradeCosts:
    """Round-trip işlem maliyeti bileşenleri (bps)."""

    taker_fee_bps: float = 10.0
    est_spread_bps: float = 2.0
    est_slippage_bps: float = 3.0

    @property
    def round_trip_bps(self) -> float:
        """Gidiş-dönüş maliyet: taker fee giriş+çıkış (2×) + bir spread + slippage."""
        return 2.0 * self.taker_fee_bps + self.est_spread_bps + self.est_slippage_bps


@dataclass(frozen=True)
class EconomicsConfig:
    costs: TradeCosts = field(default_factory=TradeCosts)
    min_net_edge_bps: float = 20.0
    min_rr: float = 1.5


@dataclass(frozen=True)
class TradeEconomics:
    """Per-trade ekonomi kapısının çıktısı (RiskDecision DEĞİL — guard'ı tetiklemez).

    `allow=True` yalnızca rr ≥ min_rr VE net_edge_bps ≥ min_net_edge_bps olduğunda.
    `reason`: ok | bad_rr | below_cost | insufficient_levels | invalid_entry | invalid_stop.
    """

    allow: bool
    reason: str
    rr: float | None = None
    reward_bps: float | None = None
    risk_bps: float | None = None
    cost_bps: float = 0.0
    net_edge_bps: float | None = None
    evidence: list[str] = field(default_factory=list)


def load_economics_config() -> EconomicsConfig:
    """`thresholds.trade_economics` bloğunu okur (yoksa spec varsayılanları)."""
    te = load_thresholds().get("trade_economics", {}) or {}
    c = te.get("costs", {}) or {}
    return EconomicsConfig(
        costs=TradeCosts(
            taker_fee_bps=float(c.get("taker_fee_bps", 10)),
            est_spread_bps=float(c.get("est_spread_bps", 2)),
            est_slippage_bps=float(c.get("est_slippage_bps", 3)),
        ),
        min_net_edge_bps=float(te.get("min_net_edge_bps", 20)),
        min_rr=float(te.get("min_rr", 1.5)),
    )


def evaluate_trade(
    entry: float | None,
    stop: float | None,
    target: float | None,
    *,
    config: EconomicsConfig | None = None,
) -> TradeEconomics:
    """Önerilen girişi maliyet + R:R açısından değerlendirir (yalnızca kısıtlayıcı).

    `allow=True` yalnızca rr ≥ min_rr VE net_edge_bps ≥ min_net_edge_bps. Eksik veya
    geçersiz seviye → `allow=False` + diagnostic reason (uydurma allow yok).
    """
    cfg = config or load_economics_config()
    cost_bps = cfg.costs.round_trip_bps

    # Eksik veri = diagnostic BLOCK (fake allow yok).
    if entry is None or stop is None or target is None:
        return TradeEconomics(
            allow=False,
            reason="insufficient_levels",
            cost_bps=round(cost_bps, 4),
            evidence=["entry/stop/target eksik — kapı varsayılan olarak kapalı"],
        )
    if entry <= 0:
        return TradeEconomics(
            allow=False,
            reason="invalid_entry",
            cost_bps=round(cost_bps, 4),
            evidence=[f"entry={entry} ≤ 0"],
        )

    risk_bps = abs(entry - stop) / entry * BPS
    reward_bps = abs(target - entry) / entry * BPS

    if risk_bps <= 0:
        return TradeEconomics(
            allow=False,
            reason="invalid_stop",
            reward_bps=round(reward_bps, 4),
            risk_bps=round(risk_bps, 4),
            cost_bps=round(cost_bps, 4),
            evidence=["stop = entry — risk tanımsız"],
        )

    rr = reward_bps / risk_bps
    net_edge_bps = reward_bps - cost_bps
    rr_ok = rr >= cfg.min_rr
    edge_ok = net_edge_bps >= cfg.min_net_edge_bps

    if not rr_ok:
        reason = "bad_rr"
    elif not edge_ok:
        reason = "below_cost"
    else:
        reason = "ok"

    return TradeEconomics(
        allow=rr_ok and edge_ok,
        reason=reason,
        rr=round(rr, 4),
        reward_bps=round(reward_bps, 4),
        risk_bps=round(risk_bps, 4),
        cost_bps=round(cost_bps, 4),
        net_edge_bps=round(net_edge_bps, 4),
        evidence=[
            f"rr {rr:.2f} (min {cfg.min_rr})",
            f"net_edge {net_edge_bps:.1f}bps = reward {reward_bps:.1f} "
            f"- cost {cost_bps:.1f} (min {cfg.min_net_edge_bps})",
        ],
    )


def tf_size_cap(timeframe: str) -> float:
    """`timeframe_risk.risk_multiplier`'dan TF size tavanı (≤1.0; yalnız küçültür).

    TF cap'in kanonik kaynağı config'tir; bu yardımcı sonucu her zaman [0, 1.0]
    aralığına sıkıştırır — üst TF ASLA scale-up yapamaz, RiskGate bypass edilemez.
    """
    tfr = load_thresholds().get("timeframe_risk", {}) or {}
    pol = tfr.get(timeframe, {}) or {}
    mult = float(pol.get("risk_multiplier", 1.0))
    return max(0.0, min(1.0, mult))
