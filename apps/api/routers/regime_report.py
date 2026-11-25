"""GET /api/v1/regime-report/current + GET /api/v1/calendar/event-outcomes"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.providers.news import rss
from packages.decision import read_model
from packages.learning import event_outcomes
from packages.regime import report as regime_report

router = APIRouter(tags=["regime"])


@router.get("/regime-report/current")
def get_regime_report_current() -> dict:
    return regime_report.current_view(read_model.current())


@router.get("/news/current")
def get_news_current(limit: int = 48) -> dict:
    """Heart Haberler sekmesi için canonical, salt-okuma haber duvarı.

    Haber duvarı artık provider'ı yeniden çağırmaz: karar snapshot'ında görülen
    başlıkların aynısını kullanır. Böylece Heart, Brain ve karar motoru farklı
    RSS döngülerinden farklı sonuçlar göstermez. ``limit`` geriye dönük olarak
    kabul edilir; snapshot penceresi daha küçükse mevcut başlık sayısı kadar
    döner ve kapsamda açıkça belirtilir.
    """
    safe_limit = max(1, min(int(limit), 96))
    snap = get_cached_snapshot()
    headlines = list(snap.headlines[:safe_limit])
    return {
        "generated_at": snap.generated_at.isoformat(),
        "snapshot_id": snap.snapshot_id,
        "headlines": [regime_report.headline_view(item) for item in headlines],
        "count": len(headlines),
        "coverage": {
            "requested_limit": safe_limit,
            "snapshot_limit": len(snap.headlines),
            "canonical": True,
            "market_feeds": len(rss.MARKET_FEEDS),
            "foreign_affairs_feeds": sum(
                1 for feed in rss.GEO_FEEDS
                if feed["source"] in rss.FOREIGN_AFFAIRS_FEED_SOURCES
            ),
            "geo_feeds": len(rss.GEO_FEEDS),
            "source_status": {
                key: value
                for key, value in snap.provider_status.items()
                if key in {"news", "geo_news"}
            },
        },
        "paper_safe": True,
        "no_execution": True,
    }


@router.get("/calendar/event-outcomes")
def get_event_outcomes() -> dict:
    """Olay-sonrası takip (salt-gözlem): yaklaşan olaylar (kesin saat), son
    açıklananların sonucu ve beklenen vs gerçekleşen asset tepkisi.

    Tick yazar (`event_outcomes.track`), bu uç yalnız okur. Karar zinciri değişmez.
    """
    return event_outcomes.viewmodel()
