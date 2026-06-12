"""Test/dev fixture başlıkları — RUNTIME'DA ASLA KULLANILMAZ.

`TEST_USE_MOCK=true` veya `NEWS_USE_FIXTURE=true` iken orchestrator bu
listeyi döner. Tüm başlıklar `verified=False` + `source="fixture"`
damgalıdır; consensus news skoru verified olmayan başlıkları SAYMAZ —
yani fixture haberler karar zincirini etkileyemez (DATA_POLICY).
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from packages.data.types import NewsHeadline, utcnow

_FIXTURE_ROWS: list[tuple[str, str | None, str, str]] = [
    # (source_hint, region, title, sentiment)
    ("Reuters", "USA", "Fed signals patience as inflation moderates", "neutral"),
    ("CoinDesk", None, "BTC ETF flows turn positive after three-week lull", "bullish"),
    ("CNBC", "USA", "Tech earnings beat, megacaps lead the tape", "bullish"),
    ("Bloomberg", "Europe", "ECB officials split on June rate cut path", "neutral"),
    ("Al Jazeera", "Middle East", "Tensions in Strait of Hormuz lift oil premium", "bearish"),
    ("Cointelegraph", None, "On-chain whale accumulation accelerates", "bullish"),
    ("WSJ", "USA", "10y yield slips below 4.3% on softer PMI", "bullish"),
    ("Reuters", "China", "Beijing announces fresh stimulus targeting property", "bullish"),
]


def list_headlines(limit: int = 14) -> list[NewsHeadline]:
    now = utcnow()
    out: list[NewsHeadline] = []
    for i, (src, region, title, sent) in enumerate(_FIXTURE_ROWS[:limit]):
        hid = hashlib.sha1(f"fixture|{title}".encode()).hexdigest()[:12]
        out.append(
            NewsHeadline(
                id=hid,
                source="fixture",
                region=region,
                ts=now - timedelta(minutes=i * 7),
                title=f"[{src}] {title}",
                sentiment=sent,  # type: ignore[arg-type]
                asset_impact={},
                verified=False,
                freshness="FRESH",
            )
        )
    return out
