"""Benzinga haber API'si — doğrudan haber ajansı başlıkları (owner anahtarı, 2026-11-13).

`BENZINGA_API_KEY` yoksa boş liste döner (sağlayıcı kapalı; AWS'de anahtar yoksa böyle kalır).
Hata/ağ sorunu asla akışı düşürmez, sahte başlık üretilmez (DATA_POLICY).

13 Kasım 2026 denemesi: anahtar REST'te çalışıyor (taze, sembol etiketli başlık), ama kapsam dar:
günde onlarca başlık, sembol/kanal süzgeçleri boş dönüyor, WebSocket akışı 3 dakikada mesaj
göndermedi. Bu yüzden yalnız genel uç (son 50 başlık) dakikada bir okunur.

Sembol etiketi: Benzinga'nın `stocks` listesi yalnız EN FAZLA 2 sembollü haberde kullanılır
(şirkete özgü haber). Piyasa özetlerindeki uzun listeler başlığın duygusunu ilgisiz sembollere
taşımasın. Yön yine başlıktan (sınıflandırıcı) gelir; Benzinga yön vermez.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from packages.data.providers.news import classify
from packages.data.types import NewsHeadline

URL = "https://api.benzinga.com/api/v2/news"
SOURCE = "Benzinga"
PAGE_SIZE = 50
TTL_SEC = 60.0
TIMEOUT_SEC = 8.0
MAX_AGE_HOURS = 24
MAX_TICKERS_FOR_TAG = 2
# Benzinga sembol adı → sistem sembolü (yalnız kayıtta olanlar etiketlenir).
_TICKER_ALIASES = {"BTC/USD": "BTCUSD", "ETH/USD": "ETHUSD", "$BTC": "BTCUSD", "$ETH": "ETHUSD"}

_LOCK = threading.Lock()
_CACHE: tuple[float, list[NewsHeadline]] | None = None
_LAST_ERROR: str | None = None


_NAME_TERMS = {"BTCUSD": ("bitcoin", "btc"), "ETHUSD": ("ethereum", "ether", "eth")}


def _move_terms(sym: str) -> tuple[str, ...]:
    """Başlıkta sembolün hareketini arayacağımız kelimeler: kod, bilinen ad, genel hisse kelimeleri."""
    names = getattr(classify, "_COMPANY_ALIASES", {}).get(sym, ())
    return (sym.lower(), *names, *_NAME_TERMS.get(sym, ()), "shares", "stock", "stocks")


def _key() -> str:
    return os.environ.get("BENZINGA_API_KEY", "").strip()


def _default_fetch(key: str) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"pageSize": PAGE_SIZE, "displayOutput": "headline", "token": key})
    req = urllib.request.Request(f"{URL}?{q}", headers={"accept": "application/json",
                                                         "User-Agent": "clean-e-yay/2.0 (paper-safe news reader)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, list) else []


def _tradeable() -> set[str]:
    try:
        from packages.data.registry import assets as asset_registry

        return {str(a.symbol).upper() for a in asset_registry.all_assets()}
    except Exception:
        return set()


def parse(items: list[dict[str, Any]], *, now: datetime | None = None,
          symbols: set[str] | None = None) -> list[NewsHeadline]:
    """Benzinga JSON → NewsHeadline (24 saatten eski ve tarihsizler atılır)."""
    now = now or datetime.now(UTC)
    known = _tradeable() if symbols is None else symbols
    out: list[NewsHeadline] = []
    for it in items:
        title = str(it.get("title") or "").strip()
        if not title or classify.is_irrelevant(title):
            continue
        try:
            ts = parsedate_to_datetime(str(it.get("created"))).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        age_h = (now - ts).total_seconds() / 3600
        if age_h > MAX_AGE_HOURS or age_h < -1:
            continue
        sentiment = classify.classify_sentiment(title)
        tickers = [str(s.get("name") or "").upper() for s in (it.get("stocks") or []) if isinstance(s, dict)]
        tickers = [_TICKER_ALIASES.get(t, t) for t in tickers if t]
        impact: dict[str, float] = {}
        if 0 < len(tickers) <= MAX_TICKERS_FOR_TAG:
            # Benzinga'nın açık sembol bilgisi önce gelir: sınıflandırıcının genel sınıf
            # eşleşmeleri ("shares" → bütün hisse ETF'leri) 4-etki sınırını doldurup onu atmasın.
            # Yön: başlık hareketi açıkça söylüyorsa o ("Nvidia shares slide" → −1), yoksa duygu.
            d = classify.direction_of(sentiment)
            for sym in tickers:
                if sym in known:
                    move = classify.stated_move(title, _move_terms(sym))
                    impact[sym] = move if move is not None else d
        for sym, value in classify.classify_asset_impact(title, sentiment).items():
            impact.setdefault(sym, value)
        out.append(NewsHeadline(
            id=hashlib.sha1(f"{SOURCE}|{title}".encode()).hexdigest()[:12],
            source=SOURCE,
            region=classify.detect_region(title),
            ts=ts,
            title=title,
            sentiment=sentiment,
            asset_impact=dict(list(impact.items())[:4]),
            url=str(it.get("url") or "") or None,
            verified=True,
            freshness=classify.freshness_of(ts, now),
        ))
    return out


def fetch_headlines(*, fetch=None, now: datetime | None = None) -> list[NewsHeadline]:
    """Son başlıklar (60 sn önbellek). Anahtar yoksa ya da hata olursa boş liste."""
    global _CACHE, _LAST_ERROR
    key = _key()
    if not key:
        return []
    with _LOCK:
        if fetch is None and _CACHE is not None and time.monotonic() - _CACHE[0] < TTL_SEC:
            return list(_CACHE[1])
    try:
        raw = (fetch or _default_fetch)(key)
        heads = parse(raw, now=now)
        _LAST_ERROR = None
    except Exception as exc:  # ağ/yetki/biçim hatası akışı düşürmez
        _LAST_ERROR = type(exc).__name__
        return []
    if fetch is None:
        from packages.data.providers.news import first_seen

        first_seen.record(f"benzinga|{PAGE_SIZE}|0", heads, group="market")
        with _LOCK:
            _CACHE = (time.monotonic(), heads)
    return heads


def last_error() -> str | None:
    return _LAST_ERROR


def reset_cache() -> None:
    global _CACHE, _LAST_ERROR
    with _LOCK:
        _CACHE = None
        _LAST_ERROR = None


__all__ = ["fetch_headlines", "last_error", "parse", "reset_cache"]
