"""CoinGecko fiyat sağlayıcı — kripto (BTC/ETH).

Demo API anahtarı (`COINGECKO_API_KEY`) varsa kimlik doğrulamalı çağrılır
(`x-cg-demo-api-key`). Hata/timeout → None döner; orchestrator DATA_UNAVAILABLE
verir (MOCK YOK, fallback YOK).

Aylık limit koruması: Demo plan 10.000 çağrı/ay. Spot fiyat sürekli 30sn'de
çağrılırsa limit ~1.5 günde biter. Bu yüzden modül seviyesinde
`COINGECKO_PRICE_TTL_SEC` (varsayılan 900sn = 15dk) TTL cache'i ile çağrı
sıklığı sabitlenir; cache içindeki taze değer ağ çağrısı yapmadan döner. Aynı
makinedeki API/tick süreçleri `data/runtime/price_cache` içindeki aynı TTL
damgasını paylaşır; bu, çoklu worker'ın ücretsiz API kotasını çoğaltmasını önler.

Toplu çağrı (2026-10-30): önbellek bayatlayınca bütün CoinGecko sembolleri tek
istekte (`ids=a,b,c`) yenilenir; eskiden her sembol ayrı istekti (3 sembol →
günde 288 çağrı). Her ağ çağrısı `quota.consume("coingecko")` ile sayılır; günlük
bütçe doluysa çağrı yapılmaz ve DATA_UNAVAILABLE akışı sürer (sahte fiyat yok).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from packages.data.providers import coingecko_auth, quota
from packages.data.registry import custom_assets
from packages.data.types import PriceQuote, utcnow
from packages.ops.store import write_text_atomic

API = "https://api.coingecko.com/api/v3/simple/price"
TIMEOUT_SEC = 4.0

# CoinGecko id ↔ bizim sembolümüz
_SYMBOL_MAP = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
}

SUPPORTED = custom_assets.DynamicSymbolSet(frozenset(_SYMBOL_MAP.keys()), "coingecko")

# Aylık ücretsiz limiti korumak için modül-seviyesi TTL cache.
_DEFAULT_TTL_SEC = 900
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, PriceQuote]] = {}
# Başarısız toplu istekten sonra bekleme: 429'da her tick yeniden denemek kotayı
# boşa yakıyordu (2026-10-30: 16 dakikada 145 çağrı). Bu sürede orkestratör
# yedek zincire geçer.
_FAIL_BACKOFF_SEC = 600.0
_FAIL_UNTIL = 0.0


def _disk_cache_path(symbol: str) -> Path:
    root = Path(os.environ.get("PRICE_CACHE_DIR", "data/runtime/price_cache"))
    return root / f"coingecko_{symbol}.json"


def _load_disk_cache(symbol: str, ttl: float) -> PriceQuote | None:
    """Processler arasında yalnız TTL içindeki doğrulanmış quote'u paylaş."""
    try:
        raw = json.loads(_disk_cache_path(symbol).read_text(encoding="utf-8"))
        quote = PriceQuote.model_validate(raw["quote"])
        # monotonic zaman süreçler arasında karşılaştırılamaz; quote.ts UTC
        # watermark'ı TTL kontrolünün otoritesidir.
        age = (datetime.now(UTC) - quote.ts).total_seconds()
        if quote.status != "OK" or quote.price is None or age < 0 or age > ttl:
            return None
        return quote
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _save_disk_cache(quote: PriceQuote, now: float) -> None:
    try:
        path = _disk_cache_path(quote.symbol)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(
            path,
            json.dumps(
                {"fetched_monotonic": now, "quote": quote.model_dump(mode="json")},
                ensure_ascii=False,
            ),
        )
    except (OSError, TypeError, ValueError):
        # Cache yazımı veri akışını durdurmaz.
        return


def _ttl_sec() -> float:
    try:
        return float(os.environ.get("COINGECKO_PRICE_TTL_SEC", _DEFAULT_TTL_SEC))
    except (TypeError, ValueError):
        return float(_DEFAULT_TTL_SEC)


def _all_ids() -> dict[str, str]:
    """Bu sağlayıcıdan fiyatı alınan bütün semboller → CoinGecko id."""
    ids = dict(_SYMBOL_MAP)
    for asset in custom_assets.all_custom():
        if asset.provider == "coingecko" and asset.ticker:
            ids[asset.symbol] = asset.ticker
    return ids


def _fetch_many(ids: dict[str, str]) -> dict[str, PriceQuote]:
    """Tek istekte birden çok sembol; kota doluysa ya da hata varsa boş döner."""
    if not ids or not quota.consume("coingecko"):
        return {}
    url = f"{API}?ids={','.join(sorted(set(ids.values())))}&vs_currencies=usd"
    data = _request_json(url)
    if data is None:
        return {}
    out: dict[str, PriceQuote] = {}
    ts = utcnow()
    for symbol, cg_id in ids.items():
        px = (data.get(cg_id) or {}).get("usd")
        if px is None:
            continue
        out[symbol] = PriceQuote(
            symbol=symbol,
            price=float(px),
            ts=ts,
            source="coingecko",
            verified=True,
            status="OK",
            fallback=False,
        )
    return out


def _request_json(url: str, *, retry_keyless: bool = True) -> dict | None:
    req = urllib.request.Request(url, headers=coingecko_auth.headers())
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(2000).decode("utf-8", "replace")
        except Exception:
            body = ""
        # Anahtarın aylık kotası doldu: aynı isteği bir kez anahtarsız genel uçtan dene.
        if coingecko_auth.note_http_error(exc.code, body) and retry_keyless and quota.consume("coingecko"):
            return _request_json(url, retry_keyless=False)
        return None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _fetch(symbol: str, cg_id: str) -> PriceQuote | None:
    return _fetch_many({symbol: cg_id}).get(symbol)


def get_quote(symbol: str) -> PriceQuote | None:
    cg_id = _SYMBOL_MAP.get(symbol) or custom_assets.ticker_for(symbol, "coingecko")
    if cg_id is None:
        return None
    global _FAIL_UNTIL
    ttl = _ttl_sec()
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached and (now - cached[0]) < ttl:
            return cached[1]
        disk = _load_disk_cache(symbol, ttl)
        if disk is not None:
            _CACHE[symbol] = (now, disk)
            return disk
        if now < _FAIL_UNTIL:
            return None  # son toplu istek başarısızdı; bekleme süresi dolmadı
    # Bayat sembolün yanında önbelleği dolmuş öteki CoinGecko sembolleri de aynı
    # istekte yenilenir (tek çağrı); taze olanlar isteğe eklenmez.
    ids = {symbol: cg_id}
    with _LOCK:
        for other, other_id in _all_ids().items():
            hit = _CACHE.get(other)
            if other != symbol and not (hit and (now - hit[0]) < ttl):
                ids[other] = other_id
    quotes = _fetch_many(ids)
    if not quotes:
        with _LOCK:
            _FAIL_UNTIL = now + _FAIL_BACKOFF_SEC
    # Yalnızca başarılı (taze) sonucu cache'le — None'ı cache'leme ki
    # bir sonraki cycle tekrar denesin (stale fallback YOK).
    for sym, quote in quotes.items():
        with _LOCK:
            _CACHE[sym] = (now, quote)
        _save_disk_cache(quote, now)
    return quotes.get(symbol)
