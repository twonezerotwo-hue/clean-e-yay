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


# ── Adaptive SL/TP — Trade Ticket için sembol/TF bazında SL/TP üretici ───────
# `evaluate_trade` yalnızca verilen (entry, stop, target) üçlüsünü doğrular.
# Bu fonksiyon ise (entry, atr, optional support/resistance) verilince SL+TP
# üretir. Adaptif kural: SL=ATR×1.5 sabit; TP = min(ATR×4.5)→max(ATR×6.75)
# aralığında, doğal direnç/destek varsa onu, yoksa ATR tabanı.
#  - Doğal hedef ATR tabanından KISA ise: rr_floor_met=False (sinyal yetersiz)
#  - Doğal hedef ATR tavanından UZAK ise: ATR tavanı kullanılır (yapı zorlanmaz)
#  - Aksi halde: doğal hedef kullanılır
@dataclass(frozen=True)
class AdaptiveTargets:
    sl: float
    tp: float
    rr: float
    sl_basis: str       # "atr" | "invalid"
    tp_basis: str       # "resistance" | "support" | "atr_floor" | "atr_max" | "below_floor" | "invalid"
    rr_floor_met: bool  # rr ≥ min_rr (yetersizse sinyal atlanmalı)
    sl_distance: float
    notes: list[str] = field(default_factory=list)


def compute_adaptive_targets(
    side: str,
    entry: float,
    atr: float,
    *,
    support: float | None = None,
    resistance: float | None = None,
    atr_mult_sl: float = 1.5,
    min_rr: float = 3.0,
    max_rr: float = 4.5,
) -> AdaptiveTargets:
    """side='long'/'short' için entry+atr ve opsiyonel S/R ile adaptif SL/TP üret.

    SL mesafesi sabit (ATR×atr_mult_sl). TP'nin minimum hedefi SL × min_rr
    (yani entry'den ATR × atr_mult_sl × min_rr uzakta), maksimumu SL × max_rr.
    Doğal hedef (long için direnç, short için destek) varsa aralık içinde
    kullanılır; aralığın altındaysa sinyal yetersiz; üstündeyse ATR tavanı.
    """
    notes: list[str] = []
    if entry <= 0 or atr <= 0:
        return AdaptiveTargets(
            sl=0.0, tp=0.0, rr=0.0,
            sl_basis="invalid", tp_basis="invalid",
            rr_floor_met=False, sl_distance=0.0,
            notes=["entry veya atr geçersiz"],
        )
    if side not in {"long", "short"}:
        return AdaptiveTargets(
            sl=0.0, tp=0.0, rr=0.0,
            sl_basis="invalid", tp_basis="invalid",
            rr_floor_met=False, sl_distance=0.0,
            notes=[f"side bilinmiyor: {side}"],
        )

    sl_distance = atr * atr_mult_sl
    tp_min_dist = sl_distance * min_rr
    tp_max_dist = sl_distance * max_rr

    if side == "long":
        sl = entry - sl_distance
        tp_min = entry + tp_min_dist
        tp_max = entry + tp_max_dist
        natural = resistance if (resistance is not None and resistance > entry) else None
        if natural is None:
            tp, tp_basis = tp_min, "atr_floor"
            notes.append("doğal direnç yok; ATR tabanı kullanıldı (1:%.1f)" % min_rr)
        elif natural < tp_min:
            # Yetersiz fırsat — sinyal atlanmalı
            rr = (natural - entry) / sl_distance
            return AdaptiveTargets(
                sl=sl, tp=natural, rr=rr,
                sl_basis="atr", tp_basis="below_floor",
                rr_floor_met=False, sl_distance=sl_distance,
                notes=[
                    "direnç %.2f, minimum 1:%.1f için %.2f gerekirdi"
                    % (natural, min_rr, tp_min),
                    "R/R yetersiz — sinyal atlanmalı",
                ],
            )
        elif natural > tp_max:
            tp, tp_basis = tp_max, "atr_max"
            notes.append("doğal direnç çok uzakta; ATR tavanı kullanıldı (1:%.1f)" % max_rr)
        else:
            tp, tp_basis = natural, "resistance"
            notes.append("doğal direnç hedef olarak kullanıldı")
    else:  # short
        sl = entry + sl_distance
        tp_min = entry - tp_min_dist
        tp_max = entry - tp_max_dist
        natural = support if (support is not None and support < entry) else None
        if natural is None:
            tp, tp_basis = tp_min, "atr_floor"
            notes.append("doğal destek yok; ATR tabanı kullanıldı (1:%.1f)" % min_rr)
        elif natural > tp_min:
            rr = (entry - natural) / sl_distance
            return AdaptiveTargets(
                sl=sl, tp=natural, rr=rr,
                sl_basis="atr", tp_basis="below_floor",
                rr_floor_met=False, sl_distance=sl_distance,
                notes=[
                    "destek %.2f, minimum 1:%.1f için %.2f gerekirdi"
                    % (natural, min_rr, tp_min),
                    "R/R yetersiz — sinyal atlanmalı",
                ],
            )
        elif natural < tp_max:
            tp, tp_basis = tp_max, "atr_max"
            notes.append("doğal destek çok uzakta; ATR tavanı kullanıldı (1:%.1f)" % max_rr)
        else:
            tp, tp_basis = natural, "support"
            notes.append("doğal destek hedef olarak kullanıldı")

    rr = abs(tp - entry) / sl_distance
    return AdaptiveTargets(
        sl=round(sl, 4),
        tp=round(tp, 4),
        rr=round(rr, 4),
        sl_basis="atr",
        tp_basis=tp_basis,
        rr_floor_met=rr >= min_rr,
        sl_distance=round(sl_distance, 4),
        notes=notes,
    )


# ── Fixed-% targets — what `packages.paper.lifecycle.open_position` ACTUALLY
# uses for automatic execution (single source of truth; lifecycle.py calls this
# instead of inlining the formula, so shadow comparisons below are guaranteed
# faithful to live behaviour, not a copy that can drift).
def compute_fixed_targets(
    symbol: str,
    side: str,
    entry: float,
    *,
    predicted_confidence: float | None = None,
    manual: bool = False,
) -> AdaptiveTargets:
    """`thresholds.paper_trading.sl_pct[symbol] × conviction tier` — the dumb,
    timeframe-blind, structure-blind formula. Reuses `AdaptiveTargets` shape so
    callers can diff it against `compute_adaptive_targets` directly."""
    from packages.paper import conviction  # local import: paper← risk would cycle at module load

    th = load_thresholds()["paper_trading"]
    tier = conviction.tier_for(None) if manual else conviction.tier_for(predicted_confidence)
    sl_pct = float(th["sl_pct"].get(symbol, 0.04)) * tier.sl_mult
    tp_pct = sl_pct * float(th["tp_rr_ratio"])
    if entry <= 0 or side not in {"long", "short"}:
        return AdaptiveTargets(
            sl=0.0, tp=0.0, rr=0.0,
            sl_basis="invalid", tp_basis="invalid",
            rr_floor_met=False, sl_distance=0.0,
            notes=["entry veya side geçersiz"],
        )
    sl = entry * (1 - sl_pct) if side == "long" else entry * (1 + sl_pct)
    tp = entry * (1 + tp_pct) if side == "long" else entry * (1 - tp_pct)
    sl_distance = abs(entry - sl)
    rr = abs(tp - entry) / sl_distance if sl_distance > 0 else 0.0
    return AdaptiveTargets(
        sl=round(sl, 4),
        tp=round(tp, 4),
        rr=round(rr, 4),
        sl_basis="fixed_pct",
        tp_basis="fixed_rr",
        rr_floor_met=True,  # tasarımca sabit RR — floor kavramı yok
        sl_distance=round(sl_distance, 4),
        notes=[f"tier={tier.name} sl_pct={sl_pct:.4f} tp_rr={th['tp_rr_ratio']}"],
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
