"""GDELT DOC 2.0 API — global haber/olay akışı (key gerektirmez).

Stdlib-only (urllib). Her hata yutulur ve boş liste döner: network fail
asla crash etmez, mock'a asla düşülmez (DATA_POLICY).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Final

from packages.data.providers.news import classify
from packages.data.types import NewsHeadline

API = "https://api.gdeltproject.org/api/v2/doc/doc"
TIMEOUT_SEC = 8.0
MAX_AGE_HOURS: Final[int] = 24
MAX_ARTICLES: Final[int] = 12

# S1-1 (2026-07-04) — başarısızlık cooldown'u. GDELT bazı ağlardan kalıcı
# erişilemez (SSL handshake 8s timeout); her news-refresh'te bu timeout'u
# yeniden yemek tick döngüsünü kilitliyordu. Hata sonrası cooldown boyunca
# fetch atlanır; status dürüstçe degraded kalır (veri uydurulmaz), süre
# dolunca yeniden denenir. 0 → cooldown kapalı (eski davranış birebir).
_last_failure_monotonic: float | None = None
_last_error: str | None = None


def _cooldown_sec() -> float:
    try:
        return float(os.environ.get("GDELT_COOLDOWN_SEC", "900"))
    except ValueError:
        return 900.0


def _in_cooldown() -> bool:
    if _last_failure_monotonic is None:
        return False
    cd = _cooldown_sec()
    return cd > 0 and (time.monotonic() - _last_failure_monotonic) < cd


def reset_cooldown() -> None:
    """Test izolasyonu: cooldown durumunu sıfırla."""
    global _last_failure_monotonic, _last_error
    _last_failure_monotonic = None
    _last_error = None

# Anahtar gerektirmeyen — finans + makro odaklı arama sorgusu.
QUERY = (
    "(markets OR economy OR fed OR inflation OR crypto OR bitcoin OR gold OR oil) "
    "sourcelang:english"
)


def default_fetch(query: str) -> str:
    qs = urllib.parse.urlencode(
        {
            "query": query,
            "mode": "artlist",
            "maxrecords": str(MAX_ARTICLES),
            "format": "json",
            "sort": "datedesc",
        }
    )
    req = urllib.request.Request(
        f"{API}?{qs}",
        headers={"User-Agent": "clean-e-yay/0.1 (paper-safe news reader)"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_seendate(raw: str) -> datetime | None:
    # GDELT formatı: "20260626T143000Z"
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def parse_articles(
    raw_json: str, *, now: datetime | None = None
) -> list[NewsHeadline]:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    articles = data.get("articles") or []
    now_utc = now or datetime.now(UTC)
    out: list[tuple[datetime, NewsHeadline]] = []
    for art in articles:
        title = (art.get("title") or "").strip()
        if not title or classify.is_irrelevant(title):
            continue
        pub_dt = _parse_seendate(art.get("seendate") or "")
        if pub_dt is None:
            continue
        age_h = (now_utc - pub_dt).total_seconds() / 3600
        if age_h > MAX_AGE_HOURS or age_h < -1:
            continue
        source = art.get("domain") or "GDELT"
        # M1 — aktif sentiment (flag kapalıyken v1, bayt-aynı); v2 gözlem alanı.
        sentiment = classify.classify_sentiment_active(title)
        hid = hashlib.sha1(f"gdelt|{source}|{title}".encode()).hexdigest()[:12]
        out.append(
            (
                pub_dt,
                NewsHeadline(
                    id=hid,
                    source=f"GDELT/{source}",
                    region=classify.detect_region(title),
                    ts=pub_dt,
                    title=title,
                    sentiment=sentiment,
                    sentiment_v2=classify.classify_sentiment_v2(title),
                    asset_impact=classify.classify_asset_impact(title, sentiment),
                    url=art.get("url") or None,
                    verified=True,
                    freshness=classify.freshness_of(pub_dt, now_utc),
                ),
            )
        )
    out.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in out]


def fetch_headlines(fetch_fn=None) -> tuple[list[NewsHeadline], str | None]:
    """Döner: (headlines, error). Hata olsa da crash etmez, boş liste döner.

    S1-1: son deneme başarısızsa cooldown penceresi boyunca ağa hiç çıkılmaz
    (boş liste + cooldown etiketli hata döner) — kalıcı-arızalı uçtan her
    seferinde timeout yemek yerine dürüst degraded + hızlı dönüş."""
    global _last_failure_monotonic, _last_error
    if _in_cooldown():
        return [], f"GDELT cooldown ({int(_cooldown_sec())}s) — son hata: {_last_error}"
    fetch = fetch_fn or default_fetch
    try:
        raw = fetch(QUERY)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _last_failure_monotonic = time.monotonic()
        _last_error = str(exc)[:120]
        return [], f"GDELT: {_last_error}"
    _last_failure_monotonic = None
    _last_error = None
    return parse_articles(raw), None
