"""Haber sağlayıcısı — mock-first. v2.1+ ile RSS feed'leri eklenecek."""
from __future__ import annotations

import hashlib
from datetime import timedelta

from packages.data.types import NewsHeadline, utcnow

_MOCK_HEADLINES: list[tuple[str, str, str, str, str]] = [
    # (source, region, title, title_tr, sentiment)
    ("Reuters", "USA", "Fed signals patience as inflation moderates",
     "Fed enflasyon yavaşlarken sabırlı tutum sergiliyor", "neutral"),
    ("CoinDesk", "global", "BTC ETF flows turn positive after three-week lull",
     "BTC ETF akışları üç haftalık duraklamanın ardından pozitife döndü", "bullish"),
    ("CNBC", "USA", "Tech earnings beat, megacaps lead the tape",
     "Teknoloji bilançoları beklentiyi aştı, mega kapitaller liderliği aldı", "bullish"),
    ("Bloomberg", "EUR", "ECB officials split on June rate cut path",
     "AMB üyeleri Haziran faiz indirimi konusunda ayrıştı", "neutral"),
    ("Al Jazeera", "MEA", "Tensions in Strait of Hormuz lift oil premium",
     "Hürmüz Boğazı'ndaki gerilim petrol primini artırıyor", "bearish"),
    ("Cointelegraph", "global", "On-chain whale accumulation accelerates",
     "Zincir üstü balina birikimi hızlanıyor", "bullish"),
    ("WSJ", "USA", "10y yield slips below 4.3% on softer PMI",
     "10y getiri zayıf PMI ile %4.3'ün altına geriledi", "bullish"),
    ("Reuters", "CHN", "Beijing announces fresh stimulus targeting property",
     "Pekin gayrimenkule yönelik yeni teşvikleri açıkladı", "bullish"),
]


def list_headlines(limit: int = 14) -> list[NewsHeadline]:
    now = utcnow()
    out: list[NewsHeadline] = []
    for i, (source, region, title, title_tr, sent) in enumerate(_MOCK_HEADLINES[:limit]):
        hid = hashlib.sha1(f"{title}|{i}".encode()).hexdigest()[:10]
        out.append(
            NewsHeadline(
                id=hid,
                source=source,
                region=region,
                ts=now - timedelta(minutes=i * 7),
                title=title,
                title_tr=title_tr,
                sentiment=sent,  # type: ignore[arg-type]
                asset_impact={},
            )
        )
    return out
