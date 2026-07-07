"""Çıkış stop-verim backtest'i (SALT-ANALİZ / read-only, canlıya dokunmaz).

Gerçek OHLCV geçmişinde (rotasyon+BTC/ETH/metal, 4 TF) sistematik entry
(trend-proxy yön: close vs SMA20; ATR-tabanlı R birimi) üretir ve bir exit-config
ızgarasını (sabit SL × trailing aktivasyon × trailing mesafe × partial_tp) bar-bar
simüle eder → her config için net/ort/medyan R + kazanç oranı + TF kırılımı.

Amaç: "sabit ve trailing stop için EN VERİMLİ aralık nedir" sorusunu KANITLA
yanıtlamak — owner çıkış config'ini (trail mesafesi, SL katı) bu araca bakarak
gözden geçirir. Config-flag YOK (ölü-flag yasağı): salt-analiz, karara/çıkışa
dokunmaz. AĞIR (binlerce entry × ızgara) → interval-kapılı (haftalık), artifact
bayatken yeniden ölçülür. Uydurma yok: barlar gerçek, entry mekanik-proxy.
"""
from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

_ENGINE = "exit_backtest_v1"
_INTERVAL_ENV = "EXIT_BACKTEST_INTERVAL_SEC"
_DEFAULT_INTERVAL_SEC = 7 * 24 * 3600

SMA_N = 20
ATR_N = 14
ATR_BASE = 1.5      # taban SL = ATR_BASE × ATR(14) = 1R
HORIZON = 40        # forward bar tavanı
ENTRY_STEP = 6      # her ENTRY_STEP barda bir entry (örneklem seyreltme)
TP_RR = 3.0

# Exit-config ızgarası (marjinal aralık analizi bu değerler üzerinden okunur).
SL_GRID = (0.75, 1.0, 1.25, 1.5, 2.0)
TRAIL_ACT_GRID = (1.0, 1.5, 2.0)
TRAIL_DIST_GRID = (0.5, 0.75, 1.0, 1.5)
PTP_GRID = ((0.0, 0.0), (1.0, 0.5), (1.0, 0.33))  # (trigger_r, close_frac); 0=kapalı


def _path() -> Path:
    return Path(os.environ.get("EXIT_BACKTEST_PATH", "data/runtime/exit_backtest.json"))


def _interval_sec() -> int:
    try:
        return int(os.environ.get(_INTERVAL_ENV, str(_DEFAULT_INTERVAL_SEC)))
    except ValueError:
        return _DEFAULT_INTERVAL_SEC


# ── simülasyon çekirdeği ────────────────────────────────────────────────────────

def _atr(bars, i):
    if i < ATR_N:
        return None
    trs = []
    for k in range(i - ATR_N + 1, i + 1):
        hi, lo, pc = bars[k].high, bars[k].low, bars[k - 1].close
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    return sum(trs) / len(trs)


def _sma(bars, i):
    if i < SMA_N:
        return None
    return sum(b.close for b in bars[i - SMA_N + 1:i + 1]) / SMA_N


def simulate(entry, unit, long, fwd, *, sl_mult, trail_act, trail_dist, ptp_trigger, ptp_frac):
    """Tek entry'yi verilen exit config'iyle bar-bar simüle et → gerçekleşen R.

    R birimi = unit (fiyat). partial_tp: trigger'da frac kapat + kalan breakeven.
    trailing: trail_act R kârdan sonra tepe∓trail_dist R. Sabit TP = TP_RR."""
    stop = entry - sl_mult * unit if long else entry + sl_mult * unit
    tp = entry + TP_RR * unit if long else entry - TP_RR * unit
    peak = entry
    realized = 0.0
    remaining = 1.0
    be = False

    def _rr(p):
        return ((p - entry) if long else (entry - p)) / unit

    for b in fwd:
        fav = b.high if long else b.low
        adv = b.low if long else b.high
        if remaining >= 1.0 and _rr(fav) >= ptp_trigger:
            realized += ptp_frac * ptp_trigger
            remaining -= ptp_frac
            if not be:
                stop = entry
                be = True
        if (fav >= tp) if long else (fav <= tp):
            return realized + remaining * TP_RR
        peak = max(peak, fav) if long else min(peak, fav)
        if _rr(peak) >= trail_act:
            ts = peak - trail_dist * unit if long else peak + trail_dist * unit
            stop = max(stop, ts) if long else min(stop, ts)
        if (adv <= stop) if long else (adv >= stop):
            return realized + remaining * _rr(stop)
    return realized + remaining * _rr(fwd[-1].close)


def _build_entries():
    """Gerçek OHLCV'den (tf, entry, unit, long, fwd) entry'leri üret."""
    from packages.data.providers.ohlcv import get_bars, history
    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS

    syms = sorted(set(ROTATION_SYMBOLS.values()) | {"BTCUSD", "ETHUSD", "XAGUSD", "XAUUSD"})
    out = []
    for s in syms:
        for tf in ("15m", "1h", "4h", "1d"):
            try:
                bars = history.merged(history.load(s, tf), get_bars(s, tf) or [])
            except Exception:
                continue
            if len(bars) < SMA_N + HORIZON + 2:
                continue
            for i in range(SMA_N, len(bars) - HORIZON - 1, ENTRY_STEP):
                atr = _atr(bars, i)
                sma = _sma(bars, i)
                if not atr or not sma or atr <= 0:
                    continue
                entry = bars[i].close
                out.append((tf, entry, ATR_BASE * atr, entry > sma,
                            bars[i + 1:i + 1 + HORIZON]))
    return out


def compute(entries=None, now: datetime | None = None) -> dict:
    """Exit-config ızgarasını gerçek-OHLCV entry'lerinde tara → verim raporu."""
    now = now or datetime.now(UTC)
    if entries is None:
        entries = _build_entries()
    n = len(entries)
    tf_counts: dict[str, int] = defaultdict(int)
    for tf, *_ in entries:
        tf_counts[tf] += 1

    rows = []
    for sl in SL_GRID:
        for ta in TRAIL_ACT_GRID:
            for td in TRAIL_DIST_GRID:
                for (pt, pf) in PTP_GRID:
                    rs = []
                    per_tf: dict[str, list] = defaultdict(list)
                    for tf, entry, unit, long, fwd in entries:
                        r = simulate(entry, unit, long, fwd, sl_mult=sl, trail_act=ta,
                                     trail_dist=td, ptp_trigger=pt if pt else 999.0, ptp_frac=pf)
                        rs.append(r)
                        per_tf[tf].append(r)
                    rows.append({
                        "sl_mult": sl, "trail_act": ta, "trail_dist": td,
                        "ptp_trigger": pt, "ptp_frac": pf,
                        "net_r": round(sum(rs), 2),
                        "avg_r": round(sum(rs) / n, 4) if n else 0.0,
                        "median_r": round(statistics.median(rs), 4) if rs else 0.0,
                        "win_rate": round(sum(1 for r in rs if r > 0) / n, 3) if n else 0.0,
                        "per_tf_avg_r": {k: round(statistics.mean(v), 4) for k, v in per_tf.items()},
                    })
    rows.sort(key=lambda d: d["avg_r"], reverse=True)

    def _marginal(key, grid):
        out = {}
        for g in grid:
            sub = [d["avg_r"] for d in rows if d[key] == g]
            out[str(g)] = round(sum(sub) / len(sub), 4) if sub else 0.0
        return out

    per_tf_best = {}
    for tf in ("15m", "1h", "4h", "1d"):
        cand = [d for d in rows if tf in d["per_tf_avg_r"]]
        if cand:
            b = max(cand, key=lambda d: d["per_tf_avg_r"][tf])
            per_tf_best[tf] = {
                "sl_mult": b["sl_mult"], "trail_act": b["trail_act"],
                "trail_dist": b["trail_dist"], "ptp": f"{b['ptp_trigger']}/{b['ptp_frac']}",
                "avg_r": b["per_tf_avg_r"][tf],
            }

    report = {
        "generated_at": now.isoformat(),
        "engine": _ENGINE,
        "entry_count": n,
        "tf_counts": dict(tf_counts),
        "atr_base": ATR_BASE, "horizon_bars": HORIZON, "tp_rr": TP_RR,
        "best_configs": rows[:10],
        "marginal": {
            "sl_mult": _marginal("sl_mult", SL_GRID),
            "trail_act": _marginal("trail_act", TRAIL_ACT_GRID),
            "trail_dist": _marginal("trail_dist", TRAIL_DIST_GRID),
            "ptp": {
                ("off" if not pt else f"{pt}R/{int(pf*100)}%"):
                round(sum(d["avg_r"] for d in rows if d["ptp_trigger"] == pt
                         and d["ptp_frac"] == pf)
                      / max(1, sum(1 for d in rows if d["ptp_trigger"] == pt
                                   and d["ptp_frac"] == pf)), 4)
                for (pt, pf) in PTP_GRID
            },
        },
        "per_tf_best": per_tf_best,
        "note": ("SALT-ANALIZ: canli cikisa dokunmaz; entry mekanik-proxy (trend), "
                 "barlar gercek. En verimli aralik marginal tablodan okunur."),
    }
    return report


def _write(report: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def run_if_due() -> dict:
    """learning_worker adımı (AĞIR — interval-kapılı). Artifact tazeyken SKIP;
    bayat/bozuk/eski-cetvel → yeniden ölç. Flag YOK (salt-analiz)."""
    try:
        p = _path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            gen = datetime.fromisoformat(str(data.get("generated_at")))
            age = (datetime.now(UTC) - gen).total_seconds()
            if data.get("engine") == _ENGINE and 0 <= age < _interval_sec():
                return {"status": "SKIP_FRESH", "age_sec": int(age)}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    rep = compute()
    _write(rep)
    return {"status": "OK", "entries": rep["entry_count"]}


def _load() -> dict | None:
    try:
        p = _path()
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def viewmodel() -> dict:
    """GET /learning/exit-backtest — en verimli stop aralığı + TF kırılımı."""
    data = _load()
    return {
        "status": "OK" if data else "NO_DATA",
        "generated_at": (data or {}).get("generated_at"),
        "entry_count": (data or {}).get("entry_count", 0),
        "tf_counts": (data or {}).get("tf_counts") or {},
        "best_configs": (data or {}).get("best_configs") or [],
        "marginal": (data or {}).get("marginal") or {},
        "per_tf_best": (data or {}).get("per_tf_best") or {},
        "shadow_only": True,
    }


__all__ = ["compute", "run_if_due", "simulate", "viewmodel"]
