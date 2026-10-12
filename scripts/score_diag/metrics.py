"""Sinyal-düzeyi istatistikler + yürütme (SL/TP/ücret) simülasyonu + portföy metrikleri.

Yürütme simülasyonu ÜRETİM kurallarını yeniden kullanır (kopya yok):
- SL/TP geometrisi : ``packages.risk.trade_economics.compute_tf_targets`` (ATR-çapalı, TF'ye göre RR)
- Çıkış kuralı     : ``packages.paper.execution_sim.bar_exit`` (kapanış-bazlı stop, acil fren, TP)
- Zaman stopu      : ``thresholds.timeframe_risk[tf].time_stop_hours`` (bar sayısına çevrilir)
Giriş: sinyal barının KAPANIŞINDA karar, bir SONRAKİ barın AÇILIŞINDA dolum (look-ahead yok).
Ücret/kayma: varlık sınıfına göre gidiş-dönüş bps (VARSAYIM — ölçüm değil; duyarlılık raporlanır).
Trailing stop modellenmez (canlıda var) — sonuçlar bu yüzden canlı PnL'in kanıtı değil, A/B kıyasıdır.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from packages.data.registry.loader import load_thresholds
from packages.data.types import OHLCVBar
from packages.paper import execution_sim
from packages.risk import trade_economics

# Gidiş-dönüş maliyet varsayımı (bps; komisyon + yarım-spread + kayma). Duyarlılık için çarpanla.
COST_BPS = {
    "index_etf": 3.0, "equity": 6.0, "oil_etf": 8.0, "fx": 4.0, "gold": 8.0, "crypto": 30.0,
}
_HOURS_PER_BAR = {"1h": 1, "4h": 4, "1d": 24}


def _time_stop_bars(tf: str) -> int:
    hours = int((load_thresholds().get("timeframe_risk") or {}).get(tf, {}).get("time_stop_hours", 0))
    if hours <= 0:
        return 10**9
    return max(1, math.ceil(hours / _HOURS_PER_BAR[tf]))


def simulate(bars: list[OHLCVBar], sig: pd.DataFrame, tf: str, series: str, asset_class: str,
             cost_mult: float = 1.0) -> list[dict]:
    """``sig``: i, side (+1/−1), size (0..1), atr — bu (seri, tf) için karar satırları.
    Aynı anda tek pozisyon; size==0 veya side==0 satırlar atlanır (WAIT)."""
    if sig.empty:
        return []
    close_based = bool((load_thresholds().get("exit_close_based_stop") or {}).get("enabled", True))
    disaster = float((load_thresholds().get("exit_close_based_stop") or {}).get("disaster_mult", 2.0))
    max_hold = _time_stop_bars(tf)
    cost = COST_BPS.get(asset_class, 5.0) * cost_mult / 1e4
    smap = {int(r.i): (int(r.side), float(r.size), float(r.atr), r) for r in sig.itertuples()
            if r.side != 0 and r.size > 0}
    trades: list[dict] = []
    pos = None
    first, last = int(sig["i"].min()), len(bars) - 1
    for j in range(first, last + 1):
        b = bars[j]
        if pos is not None and j >= pos["entry_idx"]:
            hit = execution_sim.bar_exit(
                side="long" if pos["side"] > 0 else "short", entry_price=pos["entry"], sl=pos["sl"],
                tp=pos["tp"], high=b.high, low=b.low, close=b.close,
                close_based=close_based, disaster_mult=disaster)
            fav = (b.high / pos["entry"] - 1) if pos["side"] > 0 else (1 - b.low / pos["entry"])
            adv = (1 - b.low / pos["entry"]) if pos["side"] > 0 else (b.high / pos["entry"] - 1)
            pos["mfe"] = max(pos["mfe"], fav)
            pos["mae"] = max(pos["mae"], adv)
            reason, fill = (hit if hit else (None, None))
            if reason is None and (j - pos["entry_idx"] >= max_hold or j == last):
                reason, fill = ("TIME" if j < last else "EOD"), b.close
            if reason is not None:
                gross = pos["side"] * (fill / pos["entry"] - 1.0)
                r_gross = gross / pos["sl_pct"]
                r_net = r_gross - cost / pos["sl_pct"]
                trades.append({
                    "series": series, "tf": tf, "asset_class": asset_class, "side": pos["side"],
                    "entry_i": pos["entry_idx"], "exit_i": j, "bars": j - pos["entry_idx"] + 1,
                    "entry_ts": bars[pos["entry_idx"]].ts, "exit_ts": b.ts, "reason": reason,
                    "sl_pct": pos["sl_pct"], "r_gross": r_gross, "r_net": r_net,
                    "ret_net": gross - cost, "mfe_r": pos["mfe"] / pos["sl_pct"],
                    "mae_r": pos["mae"] / pos["sl_pct"], "size": pos["size"], "sig_i": pos["sig_i"],
                })
                pos = None
        if pos is None and j in smap and j + 1 <= last:
            side, size, atr, _ = smap[j]
            entry = bars[j + 1].open
            tg = trade_economics.compute_tf_targets(
                series, "long" if side > 0 else "short", entry, timeframe=tf, atr=atr)
            if tg.sl_basis == "invalid" or tg.sl_distance <= 0:
                continue
            pos = {"side": side, "entry": entry, "sl": tg.sl, "tp": tg.tp, "size": size,
                   "sl_pct": tg.sl_distance / entry, "entry_idx": j + 1, "sig_i": j,
                   "mfe": 0.0, "mae": 0.0}
    return trades


def portfolio_metrics(tr: pd.DataFrame) -> dict:
    """Net R (size ağırlıklı) üzerinden: sayı, isabet, beklenti, PF, MaxDD, Sharpe/Sortino, ..."""
    if tr.empty:
        return {"n": 0}
    sized = tr["r_net"] * tr["size"]
    wins, losses = sized[sized > 0], sized[sized < 0]
    t = tr.sort_values("exit_ts")
    eq = (t["r_net"] * t["size"]).cumsum()
    dd = float((eq.cummax() - eq).max())
    monthly = (t.set_index("exit_ts")["r_net"] * t.set_index("exit_ts")["size"]).resample("ME").sum()
    mu, sd = float(monthly.mean()), float(monthly.std(ddof=0))
    dn = monthly[monthly < 0]
    dsd = float(math.sqrt((dn**2).mean())) if len(dn) else 0.0
    n = len(tr)
    se = float(sized.std(ddof=1) / math.sqrt(n)) if n > 2 else float("nan")
    return {
        "n": n,
        "win_rate": float((tr["r_net"] > 0).mean()),
        "avg_r_net": float(sized.mean()),
        "median_r_net": float(tr["r_net"].median()),
        "avg_r_gross": float((tr["r_gross"] * tr["size"]).mean()),
        "expectancy_t": float(sized.mean() / se) if se and se > 0 else float("nan"),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float("inf"),
        "total_r": float(sized.sum()),
        "max_dd_r": dd,
        "sharpe_m": float(mu / sd * math.sqrt(12)) if sd > 0 else float("nan"),
        "sortino_m": float(mu / dsd * math.sqrt(12)) if dsd > 0 else float("nan"),
        "avg_bars": float(tr["bars"].mean()),
        "avg_mfe_r": float(tr["mfe_r"].mean()),
        "avg_mae_r": float(tr["mae_r"].mean()),
        "fee_drag_r": float((tr["r_gross"] - tr["r_net"]).mul(tr["size"]).mean()),
        "long_n": int((tr["side"] > 0).sum()),
        "short_n": int((tr["side"] < 0).sum()),
    }


def signal_stats(df: pd.DataFrame, side: pd.Series, h: int = 10, adjust: bool = False) -> dict:
    """Sinyal düzeyi (yürütme YOK): ileri h-bar getirisi, işlem yönünde. Satırlar örtüşür →
    etkin örneklem n'den küçüktür (t-istatistiği verilmez)."""
    m = (side != 0) & df[f"f{h}"].notna()
    if not m.any():
        return {"n": 0}
    d = df[m]
    sd = side[m]
    r = sd * (d[f"f{h}"] - (d[f"drift{h}"] if adjust else 0.0))
    z = r / (d["atrp"] * math.sqrt(h))
    mfe = np.where(sd > 0, d["mfe20"], -d["mae20"])
    mae = np.where(sd > 0, -d["mae20"], d["mfe20"])
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    return {
        "n": int(m.sum()), "hit": float((r > 0).mean()), "mean_pct": float(r.mean() * 100),
        "median_pct": float(r.median() * 100), "mean_z": float(z.mean()),
        "pf": float(pos / neg) if neg > 0 else float("inf"),
        "mfe_pct": float(np.nanmean(mfe) * 100), "mae_pct": float(np.nanmean(mae) * 100),
    }


def spearman(a, b) -> float:
    """Spearman = sıra (rank) üzerinde Pearson (scipy bağımlılığı yok)."""
    a, b = pd.Series(a).reset_index(drop=True), pd.Series(b).reset_index(drop=True)
    m = a.notna() & b.notna()
    if m.sum() < 3:
        return float("nan")
    return float(a[m].rank().corr(b[m].rank()))


def fmt(d: dict, keys: list[str]) -> list[str]:
    out = []
    for k in keys:
        v = d.get(k)
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            out.append("—" if v is None or (isinstance(v, float) and math.isnan(v)) else "∞")
        elif isinstance(v, float):
            out.append(f"{v:.3f}" if abs(v) < 10 else f"{v:.1f}")
        else:
            out.append(str(v))
    return out
