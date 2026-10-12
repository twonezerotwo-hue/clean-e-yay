"""Geçmiş OHLCV veri yükleyici — QuantConnect Lean örnek veri seti (kamuya açık GitHub).

Neden bu kaynak: repoda BAR_HISTORY arşivi git'te yok (``data/runtime/`` gitignored,
sahibin makinesinde/AWS'te birikir). Bulut oturumundan erişilebilen tek çok-varlıklı,
çok-rejimli OHLCV kaynağı Lean'in ``Data/`` örnekleri: hisse/ETF (1998-2021),
FX ve altın (2006/07-2018/19), BTC (2014-2018); günlük + saatlik. Veri indirilir
(``download``), repoya KONMAZ (``data/score_diag_cache`` gitignored).

Düzeltmeler (yanlış sinyal üretmesin diye):
- Hisse fiyatları 10000 ile ölçeklidir ve BÖLÜNME-DÜZELTMESİZDİR → bilinen bölünmeler
  tabloyla (``SPLITS``) ve veride doğrulanarak geriye uygulanır.
- FX/CFD dosyaları bid+ask OHLC taşır → orta fiyat (mid) kullanılır; hacim yok (None).
"""
from __future__ import annotations

import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from packages.data.types import OHLCVBar

LEAN_BASE = "https://raw.githubusercontent.com/QuantConnect/Lean/master/Data"
DEFAULT_CACHE = Path("data/score_diag_cache")


@dataclass(frozen=True)
class Series:
    name: str          # çıktılarda görünen ad
    asset_class: str   # equity | index_etf | fx | gold | crypto | oil_etf
    path: str          # Lean Data/ altı yol (uzantısız)
    tf: str            # kaynak zaman dilimi: 1d | 1h
    kind: str          # equity | fx | crypto


SERIES: list[Series] = [
    Series("SPY", "index_etf", "equity/usa/daily/spy", "1d", "equity"),
    Series("QQQ", "index_etf", "equity/usa/daily/qqq", "1d", "equity"),
    Series("IWM", "index_etf", "equity/usa/daily/iwm", "1d", "equity"),
    Series("AAPL", "equity", "equity/usa/daily/aapl", "1d", "equity"),
    Series("IBM", "equity", "equity/usa/daily/ibm", "1d", "equity"),
    Series("BAC", "equity", "equity/usa/daily/bac", "1d", "equity"),
    Series("AIG", "equity", "equity/usa/daily/aig", "1d", "equity"),
    Series("GOOG", "equity", "equity/usa/daily/goog", "1d", "equity"),
    Series("USO", "oil_etf", "equity/usa/daily/uso", "1d", "equity"),
    Series("EURUSD", "fx", "forex/oanda/daily/eurusd", "1d", "fx"),
    Series("GBPUSD", "fx", "forex/oanda/daily/gbpusd", "1d", "fx"),
    Series("NZDUSD", "fx", "forex/oanda/daily/nzdusd", "1d", "fx"),
    Series("EURGBP", "fx", "forex/oanda/daily/eurgbp", "1d", "fx"),
    Series("XAUUSD", "gold", "cfd/oanda/daily/xauusd", "1d", "fx"),
    Series("BTCUSD", "crypto", "crypto/coinbase/daily/btcusd_trade", "1d", "crypto"),
    # saatlik kaynaklar (1h doğrudan, 4h yeniden örneklenerek)
    Series("SPY", "index_etf", "equity/usa/hour/spy", "1h", "equity"),
    Series("AAPL", "equity", "equity/usa/hour/aapl", "1h", "equity"),
    Series("IBM", "equity", "equity/usa/hour/ibm", "1h", "equity"),
    Series("BAC", "equity", "equity/usa/hour/bac", "1h", "equity"),
    Series("AIG", "equity", "equity/usa/hour/aig", "1h", "equity"),
    Series("EURUSD", "fx", "forex/oanda/hour/eurusd", "1h", "fx"),
    Series("NZDUSD", "fx", "forex/oanda/hour/nzdusd", "1h", "fx"),
    Series("XAUUSD", "gold", "cfd/oanda/hour/xauusd", "1h", "fx"),
]

# Bilinen bölünmeler: ad -> [(ilk işlem günü YYYYMMDD, oran)]; oran = yeni/eski hisse sayısı
# (2:1 bölünme -> 2.0; 1:8 ters bölünme -> 0.125). Veride sıçramayla DOĞRULANIR
# (``detect_jumps``); eşleşmeyen girdi hata verir — sessiz yanlış düzeltme olmaz.
SPLITS: dict[str, list[tuple[str, float]]] = {
    "AAPL": [("20000621", 2.0), ("20050228", 2.0), ("20140609", 7.0), ("20200831", 4.0)],
    "QQQ": [("20000320", 2.0)],
    "IWM": [("20050609", 2.0)],
    "IBM": [("19990527", 2.0)],
    "BAC": [("20040830", 2.0)],
    "AIG": [("19980803", 1.5), ("20000731", 1.5), ("20090701", 0.05)],
    "GOOG": [("20140403", 2.0)],
    "USO": [("20200429", 0.125)],
}


VIX_URL = "https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv"


def download_vix(cache: Path = DEFAULT_CACHE) -> Path:
    """CBOE VIX günlük geçmişi (kamuya açık datasets/finance-vix). Sentinel 'stres bağlamı'
    tanılaması için; üretim bar önbelleğinden bağımsız."""
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / "vix-daily.csv"
    if not dest.exists() or dest.stat().st_size < 1000:
        with urllib.request.urlopen(VIX_URL, timeout=60) as r:
            dest.write_bytes(r.read())
    return dest


def _url(path: str) -> str:
    return f"{LEAN_BASE}/{path}.zip"


def download(cache: Path = DEFAULT_CACHE) -> list[Path]:
    """Eksik zip'leri indir (var olanı yeniden indirmez). Ağ yoksa açık hata."""
    cache.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for s in SERIES:
        dest = cache / (s.path.replace("/", "_") + ".zip")
        if not dest.exists() or dest.stat().st_size < 1000:
            with urllib.request.urlopen(_url(s.path), timeout=60) as r:
                dest.write_bytes(r.read())
        out.append(dest)
    return out


def _read_csv_rows(zip_path: Path) -> list[list[str]]:
    with zipfile.ZipFile(zip_path) as z:
        name = z.namelist()[0]
        text = z.read(name).decode("utf-8")
    return [ln.split(",") for ln in text.strip().splitlines() if ln.strip()]


def _parse_ts(raw: str) -> datetime:
    fmt = "%Y%m%d %H:%M"
    return datetime.strptime(raw, fmt).replace(tzinfo=UTC)


def _rows_to_bars(s: Series, rows: list[list[str]]) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    for r in rows:
        ts = _parse_ts(r[0])
        if s.kind == "equity":
            o, h, lo, c = (float(x) / 10000.0 for x in r[1:5])
            v = float(r[5])
        elif s.kind == "fx":
            # bid O H L C vol ask O H L C vol -> mid
            o = (float(r[1]) + float(r[6])) / 2
            h = (float(r[2]) + float(r[7])) / 2
            lo = (float(r[3]) + float(r[8])) / 2
            c = (float(r[4]) + float(r[9])) / 2
            v = float(r[5]) + float(r[10])
        else:  # crypto
            o, h, lo, c = (float(x) for x in r[1:5])
            v = float(r[5])
        if not (o > 0 and h > 0 and lo > 0 and c > 0) or h < lo:
            continue
        bars.append(
            OHLCVBar(
                symbol=s.name, timeframe=s.tf, ts=ts, open=o, high=h, low=lo, close=c,
                volume=(v if v > 0 else None), source="lean_sample",
            )
        )
    return bars


def detect_jumps(bars: list[OHLCVBar], min_gap: float = 0.25) -> list[tuple[int, float]]:
    """Önceki kapanış -> bu açılış oranı 1±min_gap dışında olan barlar (bölünme adayı)."""
    out = []
    for i in range(1, len(bars)):
        prev = bars[i - 1].close
        if prev > 0:
            r = bars[i].open / prev
            if r < 1 - min_gap or r > 1 + min_gap:
                out.append((i, r))
    return out


def apply_splits(name: str, bars: list[OHLCVBar]) -> list[OHLCVBar]:
    """Bölünmeleri geriye doğru uygula (tablodaki her tarih için sıçrama doğrulanır)."""
    splits = SPLITS.get(name)
    if not splits:
        return bars
    factor_by_idx: dict[int, float] = {}
    for date, ratio in splits:
        d = datetime.strptime(date, "%Y%m%d").replace(tzinfo=UTC).date()
        idx = next((i for i, b in enumerate(bars) if b.ts.date() >= d), None)
        if idx is None or idx == 0:
            continue  # veri o tarihi kapsamıyor (ör. saatlik dosya daha kısa)
        gap = bars[idx].open / bars[idx - 1].close
        if abs(gap * ratio - 1.0) > 0.15:
            raise ValueError(f"{name} {date}: bölünme oranı {ratio} veriyle uyuşmuyor (gap={gap:.3f})")
        factor_by_idx[idx] = ratio
    out: list[OHLCVBar] = []
    cum = 1.0
    scale = [1.0] * len(bars)
    for i in range(len(bars) - 1, -1, -1):
        scale[i] = cum
        if i in factor_by_idx:
            cum *= factor_by_idx[i]
    for b, k in zip(bars, scale, strict=True):
        if k == 1.0:
            out.append(b)
            continue
        out.append(
            b.model_copy(
                update={
                    "open": b.open / k, "high": b.high / k, "low": b.low / k, "close": b.close / k,
                    "volume": (b.volume * k if b.volume is not None else None),
                }
            )
        )
    return out


def clean(bars: list[OHLCVBar]) -> tuple[list[OHLCVBar], dict[str, int]]:
    """Veri hatalarını (tek-bar sivri uç/açılış hatası) temizle; ne yapıldığını say.

    1. Açılış hatası: açılış önceki kapanıştan >%40 sapıyor ama kapanış %10 içinde -> açılış = önceki kapanış.
    2. Fitil hatası: yüksek > 1.35 x (open, close, önceki kapanış) maksimumu -> kırp (düşük için ayna).
    3. Sivri kapanış: kapanış önceki kapanıştan >%18 sapıp ertesi açılış aynı oranda geri dönüyorsa bar atılır.
    Gerçek kriz günleri (AIG 2008) bu kurallardan geçer: kayıp tek yönlüdür, geri dönmez.
    """
    stats = {"open_fixed": 0, "wick_clipped": 0, "spike_dropped": 0}
    out: list[OHLCVBar] = []
    n = len(bars)
    for i, b in enumerate(bars):
        o, h, lo, c = b.open, b.high, b.low, b.close
        prev_c = out[-1].close if out else None
        if prev_c:
            if abs(o / prev_c - 1) > 0.40 and abs(c / prev_c - 1) < 0.10:
                o = prev_c
                stats["open_fixed"] += 1
            body_hi = max(o, c, prev_c)
            body_lo = min(o, c, prev_c)
        else:
            body_hi, body_lo = max(o, c), min(o, c)
        nh, nl = h, lo
        if h > 1.35 * body_hi:
            nh = body_hi
        if lo < body_lo / 1.35:
            nl = body_lo
        nh = max(nh, o, c)
        nl = min(nl, o, c)
        if (nh, nl) != (h, lo):
            stats["wick_clipped"] += 1
        if prev_c and i + 1 < n:
            nxt_o = bars[i + 1].open
            up = c / prev_c - 1
            back = nxt_o / c - 1
            if abs(up) > 0.18 and abs(back) > 0.18 and up * back < 0:
                stats["spike_dropped"] += 1
                continue
        out.append(b.model_copy(update={"open": o, "high": nh, "low": nl}))
    return out, stats


def longest_segment(bars: list[OHLCVBar], max_gap_days: float) -> list[OHLCVBar]:
    """Zaman boşlukları (veri deliği) göstergeleri bozar -> en uzun kesintisiz parçayı al."""
    if not bars:
        return bars
    segs: list[list[OHLCVBar]] = [[bars[0]]]
    for prev, cur in pairwise(bars):
        if (cur.ts - prev.ts).total_seconds() / 86400.0 > max_gap_days:
            segs.append([])
        segs[-1].append(cur)
    return max(segs, key=len)


def load_series(s: Series, cache: Path = DEFAULT_CACHE) -> list[OHLCVBar]:
    dest = cache / (s.path.replace("/", "_") + ".zip")
    bars = _rows_to_bars(s, _read_csv_rows(dest))
    bars.sort(key=lambda b: b.ts)
    bars, _ = clean(bars)
    if s.kind == "equity":
        bars = apply_splits(s.name, bars)
    return longest_segment(bars, 15.0 if s.tf == "1d" else 10.0)


def resample_4h(bars_1h: list[OHLCVBar], kind: str, name: str) -> list[OHLCVBar]:
    """1h -> 4h. FX/altın/kripto: UTC 00/04/08/12/16/20 kutuları. Hisse: seans başına 2 kutu
    (sabah <13:00, öğleden sonra) — gece boşluğu bar içine karışmasın."""
    buckets: dict[tuple, list[OHLCVBar]] = {}
    for b in bars_1h:
        if kind == "equity":
            key = (b.ts.date(), 0 if b.ts.hour < 13 else 1)
        else:
            key = (b.ts.date(), b.ts.hour // 4)
        buckets.setdefault(key, []).append(b)
    out: list[OHLCVBar] = []
    for key in sorted(buckets):
        g = buckets[key]
        vols = [x.volume for x in g if x.volume is not None]
        out.append(
            OHLCVBar(
                symbol=name, timeframe="4h", ts=g[0].ts, open=g[0].open,
                high=max(x.high for x in g), low=min(x.low for x in g), close=g[-1].close,
                volume=(sum(vols) if vols else None), source="lean_sample",
            )
        )
    return out


def universe(cache: Path = DEFAULT_CACHE) -> dict[tuple[str, str], tuple[Series, list[OHLCVBar]]]:
    """(ad, tf) -> (seri, barlar) — 1d, 1h ve 1h'den türetilmiş 4h."""
    out: dict[tuple[str, str], tuple[Series, list[OHLCVBar]]] = {}
    for s in SERIES:
        bars = load_series(s, cache)
        out[(s.name, s.tf)] = (s, bars)
        if s.tf == "1h":
            out[(s.name, "4h")] = (s, resample_4h(bars, s.kind, s.name))
    return out
