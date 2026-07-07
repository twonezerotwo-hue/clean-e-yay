"""0-2 çizgi stratejisi karnesi (SALT-ANALİZ / read-only; canlıya dokunmaz).

Owner'ın takdirî Elliott 0-2 yönteminin (kalibrasyon: 2026-07-07, BTC 4h
canlı örneği üzerinden) mekanik karnesi. Geometri + geçerlilik kuralı
`packages/elliott/zero_two.py`'de; burada iki işlem tipi simüle edilir:

- **T1 fitil işlemi**: GECERLI setup'ta fitil değmesi (WICK_TOUCH) →
  sonraki 3 bar içinde fitil barının kırılım-yönü ucu aşılırsa o seviyeden
  KIRILIM YÖNÜNE giriş (düşen çizgi → long, yükselen → short); stop fitil
  barının öbür ucunun %0.1 ötesi. Owner hedef kuralı vermedi → 1R/2R/3R
  hedeflerinin üçü de raporlanır (zayıf sinyal / küçük poz tarafı).
- **T2 kırılım işlemi**: kapanışla geçiş (CLOSE_BREAK) → ≤10 bar içinde
  çizgiye baktest (değme + kırılım yönünde kapanış) → baktest kapanışında
  giriş; stop 0 noktasının (dalga-3 ucu) %0.1 ötesi; hedef = baktest pivotu
  + 1.618 × |J − 0| (J = kırılım bacağının ucu). Owner'ın 2 Tem BTC işlemi
  birebir bu: K girişi, D altı stop, G (1.618) çıkışı.

Config-flag YOK (ölü-flag yasağı; `exit_backtest` deseni): salt-analiz,
karara/paper'a/ağırlığa dokunmaz. Interval-kapılı (haftalık) — bar arşivi
büyüdükçe karne kendiliğinden daha uzun pencereyle ölçer. Fitilsiz barlar
(high==low; ör. CoinGecko kripto 1h/1d anlık-fiyat barları) fitil bilgisi
taşımadığından o sembol×TF atlanır ve `skipped_flat` olarak raporlanır.
"""
from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from packages.elliott import zero_two

_ENGINE = "zero_two_scorecard_v1"
_INTERVAL_ENV = "ZERO_TWO_SCORECARD_INTERVAL_SEC"
_DEFAULT_INTERVAL_SEC = 7 * 24 * 3600

_TIMEFRAMES = ("1h", "4h")
# Kripto ayrı raporlanır: owner edge'inin ana evi ("bu sektörde") + veri
# kaynağı farklı (fitil kalitesi). DODO/SKYAI custom-asset kripto arşivleri.
_CRYPTO = frozenset({"BTCUSD", "ETHUSD", "DODO", "SKYAI"})

STOP_PAD = 0.001        # stop, referans ucun %0.1 ötesi (owner kuralı)
TRIGGER_WINDOW = 3      # T1: fitil ucunun kaç bar içinde kırılması gerekir
RETEST_WINDOW = 10      # T2: kırılımdan sonra baktest için beklenen bar
FIB_EXT = 1.618         # T2 hedefi: dalga-1'in 1.618 uzantısı (owner: G çıkışı)
HORIZON = 60            # forward simülasyon tavanı (bar)
T1_TARGETS = (1.0, 2.0, 3.0)
_FLAT_MAX = 0.2         # bar penceresinde fitilsiz (high==low) oran tavanı


def _path() -> Path:
    return Path(os.environ.get("ZERO_TWO_SCORECARD_PATH", "data/runtime/zero_two_scorecard.json"))


def _interval_sec() -> int:
    try:
        return int(os.environ.get(_INTERVAL_ENV, str(_DEFAULT_INTERVAL_SEC)))
    except ValueError:
        return _DEFAULT_INTERVAL_SEC


# ── simülasyon çekirdeği (bar-bar; aynı barda stop+hedef → STOP, muhafazakâr) ──

def simulate_fixed_r(bars: list, entry_idx: int, entry: float, stop: float, long: bool) -> dict | None:
    """T1: kR hedefleri (k=1/2/3) için sonuç. Ufuk dolarsa son kapanıştan çıkış."""
    r0 = (entry - stop) if long else (stop - entry)
    if r0 <= 0 or r0 / entry < 0.0002:
        return None
    results: dict[float, float] = {}
    for k in T1_TARGETS:
        target = entry + k * r0 if long else entry - k * r0
        out: float | None = None
        for j in range(entry_idx + 1, min(len(bars), entry_idx + 1 + HORIZON)):
            b = bars[j]
            if (b.low <= stop) if long else (b.high >= stop):
                out = -1.0
                break
            if (b.high >= target) if long else (b.low <= target):
                out = k
                break
        if out is None:
            last = bars[min(len(bars) - 1, entry_idx + HORIZON)].close
            out = ((last - entry) / r0) if long else ((entry - last) / r0)
        results[k] = out
    return {"r0_pct": r0 / entry * 100, "results": results}


def simulate_fib_target(bars: list, entry_idx: int, entry: float, stop: float, target: float, long: bool) -> dict | None:
    """T2: hedef = 1.618 uzantısı, stop = 0 noktası. (r, hit, reward) döner."""
    r0 = (entry - stop) if long else (stop - entry)
    if r0 <= 0 or ((target <= entry) if long else (target >= entry)):
        return None
    reward = abs(target - entry) / r0
    for j in range(entry_idx + 1, min(len(bars), entry_idx + 1 + HORIZON)):
        b = bars[j]
        if (b.low <= stop) if long else (b.high >= stop):
            return {"r": -1.0, "hit": "stop", "reward": reward}
        if (b.high >= target) if long else (b.low <= target):
            return {"r": reward, "hit": "hedef", "reward": reward}
    last = bars[min(len(bars) - 1, entry_idx + HORIZON)].close
    r = ((last - entry) / r0) if long else ((entry - last) / r0)
    return {"r": r, "hit": "ufuk", "reward": reward}


def t1_trades(bars: list, ev: zero_two.ZeroTwoEvent) -> list[dict]:
    """Fitil işlemleri: kırılım yönüne, fitil-ucu tetikli, dar stop."""
    out: list[dict] = []
    long = ev.setup.direction == "down"
    for t in ev.touches:
        if t.kind != "WICK_TOUCH":
            continue
        bar = bars[t.bar_index]
        if bar.high <= bar.low:
            continue
        stop = bar.low * (1 - STOP_PAD) if long else bar.high * (1 + STOP_PAD)
        level = bar.high if long else bar.low
        for j in range(t.bar_index + 1, min(len(bars), t.bar_index + 1 + TRIGGER_WINDOW)):
            if (bars[j].high > level) if long else (bars[j].low < level):
                sim = simulate_fixed_r(bars, j, level, stop, long)
                if sim:
                    out.append(sim)
                break
    return out


def t2_trade(bars: list, ev: zero_two.ZeroTwoEvent) -> dict | None:
    """Kırılım işlemi: kapanış-geçiş → baktest → giriş; stop 0 noktası, hedef 1.618."""
    if ev.wave3_extreme is None:
        return None
    breaks = [t for t in ev.touches if t.kind == "CLOSE_BREAK"]
    if not breaks:
        return None
    tb = breaks[-1].bar_index
    long = ev.setup.direction == "down"
    stop = ev.wave3_extreme * (1 - STOP_PAD) if long else ev.wave3_extreme * (1 + STOP_PAD)
    for j in range(tb + 1, min(len(bars), tb + 1 + RETEST_WINDOW)):
        lv = zero_two.line_value(ev.setup, j)
        if lv <= 0:
            return None
        b = bars[j]
        if (b.close < lv) if long else (b.close > lv):
            return None  # kırılım geri alındı → işlem yok
        if (b.low <= lv) if long else (b.high >= lv):
            # Yeni sayım: 0 = dalga-3 ucu, J = kırılım bacağının ucu, K = baktest.
            if long:
                j_ext = max(x.high for x in bars[tb : j + 1])
                target = b.low + FIB_EXT * (j_ext - ev.wave3_extreme)
            else:
                j_ext = min(x.low for x in bars[tb : j + 1])
                target = b.high - FIB_EXT * (ev.wave3_extreme - j_ext)
            return simulate_fib_target(bars, j, b.close, stop, target, long)
    return None


# ── veri + rapor ────────────────────────────────────────────────────────────────

def _symbols() -> list[str]:
    """Rotasyon seti + kripto + bar arşivinde fiilen bulunan her sembol.

    Kanıt neredeyse karne orada: arşive giren yeni sembol (custom asset,
    sektör ETF'i...) sonraki koşuda kendiliğinden kapsama girer. Dizin
    sabitleri `history` modülünden (değer kopyası yok)."""
    from packages.data.providers.ohlcv import history
    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS

    syms = set(ROTATION_SYMBOLS.values()) | _CRYPTO
    try:
        arch_dir = Path(os.environ.get(history._DIR_ENV, history._DEFAULT_DIR))
        for f in arch_dir.glob("*.jsonl"):
            stem, _, tf = f.stem.rpartition("_")
            if stem and tf in _TIMEFRAMES:
                syms.add(stem)
    except OSError:
        pass
    return sorted(syms)


def compute(now: datetime | None = None) -> dict:
    """Arşiv+canlı barlarda 0-2 karnesi. Asla raise etmez (sembol hatası atlanır)."""
    now = now or datetime.now(UTC)
    from packages.data.providers.ohlcv import get_bars, history

    setup_stats: dict[str, dict[str, int]] = {
        tf: defaultdict(int) for tf in _TIMEFRAMES
    }
    t1_acc: dict[str, dict[str, list[dict]]] = {tf: defaultdict(list) for tf in _TIMEFRAMES}
    t2_acc: dict[str, dict[str, list[dict]]] = {tf: defaultdict(list) for tf in _TIMEFRAMES}
    skipped_flat: list[str] = []
    scanned: list[str] = []

    for symbol in _symbols():
        grp = "kripto" if symbol in _CRYPTO else "diger"
        for tf in _TIMEFRAMES:
            try:
                bars = history.merged(history.load(symbol, tf), get_bars(symbol, tf) or [])
            except Exception:
                continue
            if len(bars) < 60:
                continue
            flat = sum(1 for b in bars if b.high <= b.low) / len(bars)
            if flat > _FLAT_MAX:
                skipped_flat.append(f"{symbol}_{tf}")
                continue
            scanned.append(f"{symbol}_{tf}")
            for ev in zero_two.analyze(bars, max_scan_bars=80):
                setup_stats[tf]["candidates"] += 1
                if ev.status == zero_two.STATUS_WAVE1_TOUCH:
                    setup_stats[tf]["iptal_dalga1"] += 1
                    continue
                if ev.status == zero_two.STATUS_WAVE3_TOUCH:
                    setup_stats[tf]["iptal_dalga3"] += 1
                    continue
                setup_stats[tf]["gecerli"] += 1
                t1_acc[tf][grp].extend(t1_trades(bars, ev))
                t2 = t2_trade(bars, ev)
                if t2:
                    t2_acc[tf][grp].append(t2)

    def _t1_summary(sims: list[dict]) -> dict:
        n = len(sims)
        per_target = {}
        for k in T1_TARGETS:
            rs = [s["results"][k] for s in sims]
            per_target[f"{k:g}R"] = {
                "win_pct": round(sum(1 for r in rs if r >= k) / n * 100, 1) if n else 0.0,
                "stop_pct": round(sum(1 for r in rs if r == -1.0) / n * 100, 1) if n else 0.0,
                "avg_r": round(statistics.mean(rs), 3) if rs else 0.0,
            }
        return {"n": n, "targets": per_target}

    def _t2_summary(sims: list[dict]) -> dict:
        n = len(sims)
        if not n:
            return {"n": 0}
        return {
            "n": n,
            "hedef_pct": round(sum(1 for s in sims if s["hit"] == "hedef") / n * 100, 1),
            "stop_pct": round(sum(1 for s in sims if s["hit"] == "stop") / n * 100, 1),
            "ufuk_pct": round(sum(1 for s in sims if s["hit"] == "ufuk") / n * 100, 1),
            "avg_r": round(statistics.mean(s["r"] for s in sims), 3),
            "medyan_hedef_r": round(statistics.median(s["reward"] for s in sims), 2),
        }

    return {
        "generated_at": now.isoformat(),
        "engine": _ENGINE,
        "scanned": scanned,
        "skipped_flat": skipped_flat,
        "setup_stats": {tf: dict(v) for tf, v in setup_stats.items()},
        "t1_fitil": {
            tf: {grp: _t1_summary(sims) for grp, sims in by_grp.items()}
            for tf, by_grp in t1_acc.items()
        },
        "t2_kirilim": {
            tf: {grp: _t2_summary(sims) for grp, sims in by_grp.items()}
            for tf, by_grp in t2_acc.items()
        },
        "note": (
            "SALT-ANALIZ: owner'in 0-2 yontemi (dalga-1/3 degme filtresi + fitil/"
            "kirilim islemleri). Canli karara dokunmaz. skipped_flat = fitilsiz "
            "veri (gercek OHLC kaynagi gelince kendiliginden kapsama girer)."
        ),
    }


def _write(report: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def run_if_due() -> dict:
    """learning_worker adımı (interval-kapılı, haftalık). Artifact tazeyken SKIP;
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
    return {
        "status": "OK",
        "scanned": len(rep["scanned"]),
        "skipped_flat": len(rep["skipped_flat"]),
    }


__all__ = [
    "compute",
    "run_if_due",
    "simulate_fib_target",
    "simulate_fixed_r",
    "t1_trades",
    "t2_trade",
]
