"""Binance klines OHLCV adapter — kripto için GERÇEK fitilli barlar (opt-in).

Neden: CoinGecko market_chart fiyat NOKTASI döner; 1h/1d kripto barları
fiilen fitilsizdir (o≈h≈l≈c, kapanış anlık görüntüsü) ve 4h bunlardan
resample edilir — fitilleri gerçek değildir. Elliott 0-2 çizgisi edge'i
fitil-hassasiyetli (fitil değmesi vs kapanış-geçişi ayrımı stop/pozisyon
kuralını belirler); fitilsiz barla kripto'da ölçülemez. Binance
`/api/v3/klines` gerçek OHLC + bar hacmi verir ve API anahtarı GEREKTİRMEZ.

Flag: `BINANCE_OHLCV_ENABLED` (env, DEFAULT OFF). OFF → orchestrator bu
modülü hiç denemez, sistem bayt-aynı (CoinGecko yolu değişmez). ON →
kripto sembolleri önce buradan denenir; hata / geo-engel / parite listede
yok → None → orchestrator CoinGecko'ya düşer (DATA_POLICY: mock yok,
stale-cache kuralı aynı).

Host sırası: `api.binance.com` bazı bölgelerde 451 döner;
`data-api.binance.vision` aynı klines sözleşmesini sunan anahtarsız
salt-market-data aynasıdır — sırayla denenir.

Not: 4h ve 1w bu kaynakta NATIVE'dir (resample değil) — fitiller gerçek.
Son kline oluşum hâlindedir; diğer provider'larla tutarlı olarak DÖNER,
arşive girmesini `history.append_new` (son barı atar) engeller.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from packages.data.providers.ohlcv import coingecko
from packages.data.types import OHLCVBar, Timeframe

FLAG = "BINANCE_OHLCV_ENABLED"
_ENV_TRUE = frozenset({"1", "true", "yes", "on"})

HOSTS = (
    "https://api.binance.com",
    "https://data-api.binance.vision",
)
TIMEOUT_SEC = 6.0

# Kripto evreni TEK kaynaktan: CoinGecko'nun statik+custom sembol kümesi.
# Binance ayrı bir evren tanımlamaz — aynı sembollerin veri-KALİTE yükseltmesidir
# (yeni sembol eklemek yine custom_assets/coingecko üzerinden yürür).
SUPPORTED = coingecko.SUPPORTED

# Açık eşleme; listede olmayanlar için USD(T) soneki heuristiği (_ticker_for).
_SYMBOL_MAP = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
}

# TF → (binance interval, limit). Tek istek (API üst sınırı 1000); kalıcı
# pencere büyümesini arşiv katmanı (history.py) sağlar. 4h/1w NATIVE.
_TF_PLAN: dict[str, tuple[str, int]] = {
    "15m": ("15m", 400),
    "1h": ("1h", 1000),
    "4h": ("4h", 600),
    "1d": ("1d", 600),
    "1w": ("1w", 400),
}

NATIVE_TFS = frozenset(_TF_PLAN.keys())

# Binance'te listelenmeyen pariteler (HTTP 400, code -1121) bir süre yeniden
# denenmez — her get_bars turunda boşa istek gitmez, orchestrator anında
# CoinGecko'ya düşer. Süreç-içi negatif cache; kalıcı değildir.
_INVALID_SYMBOL_CODE = -1121
_UNLISTED_TTL_SEC = 6 * 3600.0
_UNLISTED_LOCK = threading.Lock()
_UNLISTED: dict[str, float] = {}


def enabled() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in _ENV_TRUE


def _ticker_for(symbol: str) -> str | None:
    mapped = _SYMBOL_MAP.get(symbol)
    if mapped:
        return mapped
    base = "".join(ch for ch in symbol.upper() if ch.isalnum())
    for suffix in ("USDT", "USD"):
        if base.endswith(suffix) and len(base) > len(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base}USDT" if base else None


def _is_unlisted(ticker: str) -> bool:
    with _UNLISTED_LOCK:
        stamped = _UNLISTED.get(ticker)
        if stamped is None:
            return False
        if (time.monotonic() - stamped) >= _UNLISTED_TTL_SEC:
            del _UNLISTED[ticker]
            return False
        return True


def _mark_unlisted(ticker: str) -> None:
    with _UNLISTED_LOCK:
        _UNLISTED[ticker] = time.monotonic()


def _fetch_klines(ticker: str, interval: str, limit: int) -> list | None:
    """Ham kline satırları; ağ/sunucu hatasında None (host'lar sırayla denenir).
    Parite listede değilse (-1121) negatif-cache'e damgalar ve None döner."""
    qs = f"symbol={ticker}&interval={interval}&limit={limit}"
    for host in HOSTS:
        req = urllib.request.Request(
            f"{host}/api/v3/klines?{qs}",
            headers={"User-Agent": "clean-e-yay/0.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 400:
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                except (OSError, ValueError):
                    body = None
                if isinstance(body, dict) and body.get("code") == _INVALID_SYMBOL_CODE:
                    _mark_unlisted(ticker)
                    return None
            continue  # 451/403/5xx/diğer 400 → sıradaki host
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list) and data:
            return data
    return None


def get_bars(symbol: str, timeframe: Timeframe) -> list[OHLCVBar] | None:
    plan = _TF_PLAN.get(timeframe)
    if plan is None:
        return None
    ticker = _ticker_for(symbol)
    if ticker is None or _is_unlisted(ticker):
        return None
    interval, limit = plan
    rows = _fetch_klines(ticker, interval, limit)
    if rows is None:
        return None
    bars: list[OHLCVBar] = []
    for row in rows:
        # Kline satırı: [openTime(ms), open, high, low, close, volume, ...]
        try:
            ts_ms = float(row[0])
            o, h, lo, c, v = (float(row[i]) for i in range(1, 6))
        except (TypeError, ValueError, IndexError):
            continue
        bars.append(
            OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                ts=datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC),
                open=o,
                high=h,
                low=lo,
                close=c,
                volume=v,
                source="binance",
                verified=True,
            )
        )
    return bars or None
