"""Phase 2 — deterministic paper execution simulation (mark-to-market + fills).

The single, formalized source of the paper account's price->PnL arithmetic:
mark-to-market (unrealized) PnL, realized fill PnL, and SL/TP fill triggers. The
lifecycle owns orchestration (status transitions, audit, time-stop timing, price
sanity) and delegates the numbers here.

Fill model (preserved from lifecycle): a protective level fills at the *observed
tick price*, not at the SL/TP level — a conservative paper assumption. SL is checked
before TP.

PAPER_SAFE / NO_EXECUTION. This module ONLY computes. Every input is passed in
explicitly (primitives) — there is no PaperState/Position parameter, so it cannot
open, close, resize, or mutate a trade. It never touches a broker, never reads
live/network data, and places no orders. A "fill" here is a simulated paper fill
price, never a real execution.
"""
from __future__ import annotations

from dataclasses import dataclass

# Exit reasons produced by a *price-triggered* fill. Time-stop / kill-switch exits
# are timing/risk concerns owned by lifecycle; their PnL still routes through
# realized_pnl below, so the fill arithmetic stays single-sourced.
SL_HIT = "SL_HIT"
TP_HIT = "TP_HIT"


def unrealized_pnl(
    side: str, entry_price: float, current_price: float, size_usd: float
) -> float:
    """Mark-to-market PnL (USD) of an open position at `current_price`. Pure.

    Same formula the realized fill uses, evaluated at the current mark.
    """
    move = (
        (current_price - entry_price)
        if side == "long"
        else (entry_price - current_price)
    )
    return move / entry_price * size_usd


def realized_pnl(
    side: str, entry_price: float, exit_price: float, size_usd: float
) -> float:
    """Realized PnL (USD) of a paper fill at `exit_price`. Pure."""
    return unrealized_pnl(side, entry_price, exit_price, size_usd)


def triggered_exit(
    side: str, sl: float | None, tp: float | None, price: float,
    *, sl_trigger_price: float | None = None,
) -> str | None:
    """Which protective level `price` fills, if any — SL checked before TP
    (preserves lifecycle ordering). Returns SL_HIT / TP_HIT / None. Pure.

    `sl_trigger_price` (P2, opsiyonel): verilirse SL kontrolü tick `price` yerine
    BU fiyatla yapılır — kapanış-bazlı stop için pozisyonun TF-bar KAPANIŞI geçilir.
    5y backtest: fitil-tetikli stop yerine kapanış-tetikli stop-avını bağışıklıyor
    (toplam R +93→+596). None (default) → mevcut fitil davranışı BAYT-AYNI. TP her
    zaman tick `price` ile (kâr al fitille; owner kuralı yalnız STOP için kapanış)."""
    sl_check = sl_trigger_price if sl_trigger_price is not None else price
    if sl is not None and (
        (side == "long" and sl_check <= sl) or (side == "short" and sl_check >= sl)
    ):
        return SL_HIT
    if tp is not None and (
        (side == "long" and price >= tp) or (side == "short" and price <= tp)
    ):
        return TP_HIT
    return None


@dataclass(frozen=True)
class Fill:
    """A simulated paper fill: reason, fill price, realized PnL. A frozen value
    object — producing one opens/closes nothing and mutates nothing."""

    reason: str
    fill_price: float
    pnl_usd: float


def simulate_exit_fill(
    *,
    side: str,
    entry_price: float,
    sl: float | None,
    tp: float | None,
    size_usd: float,
    price: float,
    sl_trigger_price: float | None = None,
) -> Fill | None:
    """If `price` triggers SL/TP, return the simulated Fill (filled at the observed
    price); else None. Pure — no side effects, no state, no orders.

    `sl_trigger_price` (P2, opsiyonel): kapanış-bazlı stop — SL tetikleme bu fiyatla
    (bar kapanışı) kontrol edilir; None → mevcut fitil davranışı bayt-aynı. SL tetikte
    fill, muhafazakâr biçimde stop seviyesinin ötesindeki tetik fiyatından olur (gerçek
    kapanış dolgusu; tick `price` genelde daha lehte olurdu → uydurma kazanç yok)."""
    reason = triggered_exit(side, sl, tp, price, sl_trigger_price=sl_trigger_price)
    if reason is None:
        return None
    # Kapanış-bazlı SL dolumu: fill = tetik (kapanış) fiyatı, tick değil (muhafazakâr).
    fill_price = (
        sl_trigger_price if (reason == SL_HIT and sl_trigger_price is not None) else price
    )
    return Fill(
        reason=reason,
        fill_price=fill_price,
        pnl_usd=realized_pnl(side, entry_price, fill_price, size_usd),
    )


def disaster_level(side: str, entry_price: float | None, sl: float | None, mult: float) -> float | None:
    """H2 acil fren seviyesi: SL'nin `mult-1` risk mesafesi ötesi (long: altı, short: üstü).
    Canlı lifecycle ve bar-düzeyi backtest aynı formülü kullanır. Pure."""
    if sl is None or entry_price is None or entry_price <= 0:
        return None
    extra = (mult - 1.0) * abs(entry_price - sl)
    return sl - extra if side == "long" else sl + extra


def bar_exit(
    *,
    side: str,
    entry_price: float,
    sl: float | None,
    tp: float | None,
    high: float,
    low: float,
    close: float,
    close_based: bool,
    disaster_mult: float = 2.0,
) -> tuple[str, float] | None:
    """Canlı çıkış kurallarının KAPANMIŞ bir bar içindeki karşılığı (backtest için).

    close_based=False → fitil stopu: SL önce, sonra TP; dolum seviyede.
    close_based=True (canlı ayar) → bar içinde sırasıyla:
      1. acil fren: fitil `disaster_level`'e değerse SL_HIT, dolum o seviyede;
      2. TP: fitil hedefe değerse TP_HIT (canlıda TP tick'le, bar kapanmadan olur);
      3. kapanış stopu: bar KAPANIŞI SL'nin ötesindeyse SL_HIT, dolum kapanışta
         (canlı `simulate_exit_fill` ile aynı: tetik kapanış fiyatı).
    Bar içi sıra bilinmediğinde muhafazakâr: fren TP'den önce. Pure."""
    long = side == "long"
    if not close_based:
        if sl is not None and ((long and low <= sl) or (not long and high >= sl)):
            return SL_HIT, sl
        if tp is not None and ((long and high >= tp) or (not long and low <= tp)):
            return TP_HIT, tp
        return None
    lvl = disaster_level(side, entry_price, sl, disaster_mult)
    if lvl is not None and ((long and low <= lvl) or (not long and high >= lvl)):
        return SL_HIT, lvl
    if tp is not None and ((long and high >= tp) or (not long and low <= tp)):
        return TP_HIT, tp
    if sl is not None and ((long and close <= sl) or (not long and close >= sl)):
        return SL_HIT, close
    return None


__all__ = [
    "SL_HIT",
    "TP_HIT",
    "Fill",
    "bar_exit",
    "disaster_level",
    "realized_pnl",
    "simulate_exit_fill",
    "triggered_exit",
    "unrealized_pnl",
]
