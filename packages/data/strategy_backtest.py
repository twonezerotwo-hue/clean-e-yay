"""Strateji backtest (pilot) — canlı teknik skor motorunu geçmiş OHLCV barları
üzerinde yeniden çalıştırıp, gerçek paper-trading SL/TP kurallarıyla pozisyon
aç/kapat simülasyonu yapar ve gerçekleşmiş win rate üretir.

Kapsam (pilot, bilinçli sınırlı): sadece teknik skor (RSI/MACD/EMA/location/
pattern/volume — `packages.data.providers.technical.timeframe.build_timeframe_result`
ile CANLI sistemin kullandığı AYNI fonksiyon). Fundamental/news/sentinel modülleri
için geçmişe ait gerçek veri saklanmadığından dahil edilmez — sahte/varsayılan
değerle doldurmak yanıltıcı olur (DATA_POLICY).

Look-ahead yok: her adımda sadece o ana kadar kapanmış barlar görülür
(`bars[: i + 1]`). SL/TP gerçek paper-trading eşikleriyle aynı
(`config/thresholds_v1.0.yaml: paper_trading.sl_pct` / `tp_rr_ratio`), fill
mantığı `packages.paper.execution_sim` ile aynı formülü kullanır.

PAPER_SAFE / NO_EXECUTION — gerçek emir yok, sadece simülasyon; paper state'e
hiçbir şey yazmaz.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.providers.ohlcv import get_bars
from packages.data.providers.technical.timeframe import build_timeframe_result
from packages.data.registry import assets as asset_registry
from packages.data.registry.loader import load_thresholds
from packages.paper import execution_sim

STATUS_OK = "ok"
STATUS_INSUFFICIENT_BARS = "insufficient_bars"

# EMA200/ADX warm-up için minimum görülmüş geçmiş bar sayısı.
_WARMUP_BARS = 210


@dataclass
class SimTrade:
    side: str
    entry_ts: str
    entry_price: float
    exit_ts: str
    exit_price: float
    exit_reason: str
    pnl_pct: float
    bars_held: int


def _sl_tp_pct(symbol: str) -> tuple[float, float]:
    th = load_thresholds()["paper_trading"]
    sl_pct = float(th["sl_pct"].get(symbol, 0.04))
    tp_pct = sl_pct * float(th["tp_rr_ratio"])
    return sl_pct, tp_pct


def run_signal_backtest(symbol: str = "BTCUSD", timeframe: str = "1d") -> dict:
    """Tek sembol/TF — canlı teknik bias motoruyla üretilmiş sinyal + gerçek
    SL/TP kuralıyla simüle edilmiş trade zinciri. Aynı anda tek pozisyon
    (overlap yok); ardışık aynı yönlü bar yeni pozisyon açmaz."""
    bars = get_bars(symbol, timeframe)
    if not bars or len(bars) < _WARMUP_BARS + 5:
        return {
            "status": STATUS_INSUFFICIENT_BARS,
            "symbol": symbol,
            "timeframe": timeframe,
            "bars_available": len(bars or []),
            "bars_required": _WARMUP_BARS + 5,
        }

    sl_pct, tp_pct = _sl_tp_pct(symbol)
    trades: list[SimTrade] = []
    open_side: str | None = None
    entry_price = 0.0
    entry_ts = ""
    entry_idx = 0
    sl = tp = 0.0

    for i in range(_WARMUP_BARS, len(bars)):
        window = bars[: i + 1]
        bar = window[-1]

        if open_side is not None:
            hit: tuple[str, float] | None = None
            if open_side == "long":
                if bar.low <= sl:
                    hit = (execution_sim.SL_HIT, sl)
                elif bar.high >= tp:
                    hit = (execution_sim.TP_HIT, tp)
            else:
                if bar.high >= sl:
                    hit = (execution_sim.SL_HIT, sl)
                elif bar.low <= tp:
                    hit = (execution_sim.TP_HIT, tp)
            if hit is not None:
                reason, fill_price = hit
                pnl_pct = (
                    (fill_price - entry_price) / entry_price
                    if open_side == "long"
                    else (entry_price - fill_price) / entry_price
                )
                trades.append(
                    SimTrade(
                        side=open_side,
                        entry_ts=entry_ts,
                        entry_price=round(entry_price, 6),
                        exit_ts=bar.ts.isoformat(),
                        exit_price=round(fill_price, 6),
                        exit_reason=reason,
                        pnl_pct=round(pnl_pct, 5),
                        bars_held=i - entry_idx,
                    )
                )
                open_side = None
            continue  # aynı barda yeni pozisyon açılmaz

        result = build_timeframe_result(symbol, timeframe, window)
        bias = result.timeframe_summary.bias
        if bias == "BULLISH":
            open_side = "long"
        elif bias == "BEARISH":
            open_side = "short"
        else:
            continue
        entry_price = bar.close
        entry_ts = bar.ts.isoformat()
        entry_idx = i
        sl = entry_price * (1 - sl_pct) if open_side == "long" else entry_price * (1 + sl_pct)
        tp = entry_price * (1 + tp_pct) if open_side == "long" else entry_price * (1 - tp_pct)

    n = len(trades)
    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]
    gross_profit = sum(t.pnl_pct for t in wins)
    gross_loss = abs(sum(t.pnl_pct for t in losses))

    return {
        "status": STATUS_OK,
        "symbol": symbol,
        "timeframe": timeframe,
        "scope": "technical_only",
        "bars_used": len(bars),
        "window": {
            "from": bars[_WARMUP_BARS].ts.isoformat(),
            "to": bars[-1].ts.isoformat(),
        },
        "total_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n, 4) if n else None,
        "avg_return_pct": round(sum(t.pnl_pct for t in trades) / n, 5) if n else None,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        "trades": [vars(t) for t in trades],
    }


def run_signal_backtest_all(timeframe: str = "1d") -> dict:
    """İşlem evrenindeki (`asset_registry.trade_symbols()`) HER sembol için
    pilotu çalıştırır — statik 4 asset + role=trade ile eklenmiş her custom
    asset dahil, otomatik (sembol listesi her çağrıda taze okunur, yeni
    eklenen asset kod değişikliği gerekmeden dahil olur)."""
    per_symbol: dict[str, dict] = {}
    for symbol in asset_registry.trade_symbols():
        per_symbol[symbol] = run_signal_backtest(symbol=symbol, timeframe=timeframe)

    ok = [r for r in per_symbol.values() if r["status"] == STATUS_OK]
    total_trades = sum(r["total_trades"] for r in ok)
    all_wins = sum(r["wins"] for r in ok)

    return {
        "status": STATUS_OK if ok else STATUS_INSUFFICIENT_BARS,
        "timeframe": timeframe,
        "scope": "technical_only",
        "symbols_evaluated": len(ok),
        "symbols_total": len(per_symbol),
        "total_trades": total_trades,
        "overall_win_rate": round(all_wins / total_trades, 4) if total_trades else None,
        "per_symbol": per_symbol,
    }
