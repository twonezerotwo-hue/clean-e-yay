"""GET /api/v1/cockpit/brief — UX1 Agent Operating Cockpit ViewModel.

Tek çağrıda ilk-ekran cockpit'i besler: AgentBrief (özet beyin) + DecisionTrace
(candidate→final karar izi). Yalnızca mevcut state'i okur ve sadeleştirir —
yeni karar / emir / live çağrı YOK. Karar zinciri (decide_matrix + matrix_view)
diğer endpoint'lerle aynıdır; bu router sadece özet üretir. PAPER_SAFE.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from fastapi import APIRouter

from packages.agent.briefing import _engine_health as agent_engine_health
from packages.agent.briefing import build_executive
from packages.agent.llm.premium_brief import build_premium_brief
from packages.agent.llm.world_report import build_world_brief
from packages.agent.localization import localize_headline
from packages.causal.engine import build_shadow
from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.provenance import data_provenance
from packages.data.providers.news import classify as news_classify
from packages.data.providers.news import get_provider_status
from packages.data.providers.news import rss as news_rss
from packages.data.providers.news.provenance import build_consensus
from packages.data.registry import assets as asset_registry
from packages.decision import paper_policy
from packages.decision.cockpit import agent_brief_view, decision_trace_view
from packages.decision.engine import decide_matrix, matrix_view
from packages.paper import news_setup
from packages.paper import state as paper_state
from packages.portfolio import build_portfolio_risk
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput
from packages.world_state.engine import build as build_world_state

router = APIRouter(tags=["cockpit"])

_log = logging.getLogger("api.cockpit")
_BRIEF_TTL_SEC = max(1.0, float(os.environ.get("COCKPIT_BRIEF_CACHE_SEC", "10")))
_BRIEF_CACHE: tuple[float, dict] | None = None
_BRIEF_CACHE_LOCK = threading.Lock()
_BRIEF_REFRESHING = False


def _build_cockpit_brief() -> dict:
    snap = get_cached_snapshot()
    ps = paper_state.load()
    matrix_symbols = asset_registry.trade_symbols()
    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
        daily_anchor_date=ps.daily_anchor_date,
    )
    regime, risk, decisions = decide_matrix(
        matrix_symbols,
        snap,
        risk_in,
        open_positions=ps.open_positions,
        paper_exploration=paper_policy.enabled(),
    )
    view = matrix_view(regime, risk, decisions, snap, matrix_symbols)
    # The embedded matrix carries the same provenance as its parent envelope;
    # clients can reject a stale standalone response instead of merging it.
    view["snapshot_id"] = getattr(snap, "id", None) or getattr(snap, "snapshot_id", None)
    view["snapshot_generated_at"] = snap.generated_at.isoformat()
    view["paper_state_revision"] = getattr(ps, "revision", None)
    provenance = data_provenance(snap)
    halt_active = bool(halt_store.active_halts())
    world_state = build_world_state(snap)
    try:
        from packages.discovery import ideas as idea_board

        idea_context = idea_board.brief_context(limit=3)
    except Exception:
        # Brain brief never becomes unavailable because the optional discovery
        # board is empty or mid-refresh.
        idea_context = {"ideas": []}
    legacy_scores: dict[str, dict[str, object]] = {}
    conflict_inputs: dict[str, dict[str, object]] = {}
    for decision in decisions:
        key = f"{decision.symbol}|{decision.timeframe}"
        legacy_scores[key] = {
            "score": decision.consensus.score,
            "direction": decision.consensus.direction,
            "timeframe": decision.timeframe,
        }
        if decision.timeframe == "1d":
            legacy_scores[decision.symbol] = legacy_scores[key]
            conflict_inputs[decision.symbol] = {
                "dqs_status": "OK" if snap.quality.status == "OK" else "DEGRADED",
                "risk_gate_action": risk.action,
                "trigger_confirmed": bool(decision.actionable),
                "trade_economics_valid": None,
                "rr_context_unavailable": True,
                "setup_type": "SETUP" if decision.candidate_action != "hold" else "NO_TRADE",
                # Not (temizlik H15): eskiden meta_gate hükmünden "AVOID" aranıyordu;
                # meta_gate yalnız TAKE/SKIP ürettiği için değer HEP False/None'du.
                # meta_gate söküldü; çıktı bayt-aynı korunur (aday → False, değil → None).
                "historical_edge_strong_negative": False if decision.candidate_action in ("open_long", "open_short") else None,
                "size_multiplier": decision.size_multiplier,
                "alignment_status": "ALIGNED" if decision.consensus.confluence_aligned else "PARTIAL",
            }
    causal_shadow = build_shadow(
        world_state,
        matrix_symbols,
        technicals=snap.technicals_by_tf or snap.technicals,
        prices={quote.symbol: quote for quote in snap.prices},
        volatility=snap.volatility,
        legacy_scores=legacy_scores,
        conflict_inputs=conflict_inputs,
    )
    portfolio_risk = build_portfolio_risk(
        ps,
        impacts={impact.symbol: impact for impact in causal_shadow.impacts},
    )
    world_brief = build_world_brief(
        headlines=snap.headlines,
        world_state=world_state.to_dict(),
        causal_shadow=causal_shadow.to_dict(),
        portfolio_risk=portfolio_risk.to_dict(),
        risk_gate={"action": risk.action, "reason": risk.reason},
        dqs={"status": snap.quality.status, "score": snap.quality.score},
        # Cockpit ilk ekranı yerel LLM üretimini beklemez. Yapısal dünya kanıtı
        # ve deterministik fallback hemen döner; ayrıntılı World Brief paneli
        # kendi isteğinde tam anlatıyı üretmeye devam eder.
        allow_llm=False,
    )
    # Layer-0 yönetici metni de bu endpoint'in aynı snapshot/pozisyon state'ini
    # kullanır. Ayrı /agent/briefing hesabı dashboard'da aday ve pozisyonun
    # farklı cycle'lardan görünmesine neden olabiliyordu.
    engine = agent_engine_health()
    executive = build_executive(
        snap,
        regime,
        view.get("cells") or [],
        engine,
        world_state,
        paper_state_obj=ps,
        idea_context=idea_context,
    )
    # Cockpit is the authoritative read model for the first-screen panels.
    # Keep the complete decision matrix, prices and headlines in this same
    # snapshot envelope so a client never has to merge different cycles.
    prices = [
        {
            "symbol": quote.symbol,
            "price": quote.price,
            "ts": quote.ts.isoformat(),
            "source": quote.source,
            "verified": quote.verified,
            "status": quote.status,
            "error": quote.error,
            "fallback": quote.fallback,
        }
        for quote in snap.prices
    ]
    headlines = [
        {
            "id": headline.id,
            "source": headline.source,
            "region": headline.region,
            "countries": list(news_classify.detect_regions(headline.title)),
            "ts": headline.ts.isoformat(),
            "title": headline.title,
            # API polling is hot-path; full local translation is performed for
            # the executive brief only. This deterministic fallback keeps the
            # headline list responsive when a new feed brings many titles.
            "title_tr": localize_headline(headline, use_model=False),
            "sentiment": headline.sentiment,
            "asset_impact": headline.asset_impact,
            "actionable": bool(headline.asset_impact),
            "freshness": headline.freshness,
        }
        for headline in snap.headlines
    ]
    # Haber kanıtı için tek, ortak provenance görünümü. Bu salt-okuma raporu
    # farklı haberleri aynı varlık puanına sessizce eritmez; proxy/query
    # kutularını bağımsız yayıncı saymaz ve çelişkiyi MIXED olarak korur.
    news_consensus = build_consensus(snap.headlines)
    idea_rows = list(idea_context.get("ideas") or {}) if isinstance(idea_context, dict) else []
    news_consensus["idea_board"] = {
        "generated_at": idea_context.get("generated_at") if isinstance(idea_context, dict) else None,
        "ideas": len(idea_rows),
        "directional": sum(1 for row in idea_rows if (row.get("news") or {}).get("direction") in {"up", "down"}),
        "conflicts": sum(1 for row in idea_rows if (row.get("news") or {}).get("conflict")),
        "article_enriched": sum(int((row.get("news") or {}).get("article_enriched") or 0) for row in idea_rows),
    }
    try:
        from packages.discovery import scanner as discovery_scanner

        discovery_cfg = discovery_scanner.load_config()
        extra_feeds = tuple(
            str(item.get("url"))
            for item in (discovery_cfg.get("news_discovery") or {}).get("extra_feeds") or ()
            if isinstance(item, dict) and item.get("url")
        )
    except Exception:
        extra_feeds = ()
    base_urls = {str(item.get("url")) for item in (*news_rss.MARKET_FEEDS, *news_rss.GEO_FEEDS)}
    news_consensus["feed_inventory"] = {
        "market_feeds": len(news_rss.MARKET_FEEDS),
        "geo_feeds": len(news_rss.GEO_FEEDS),
        "foreign_affairs_feeds": sum(
            1 for feed in news_rss.GEO_FEEDS
            if feed["source"] in news_rss.FOREIGN_AFFAIRS_FEED_SOURCES
        ),
        "discovery_topic_feeds": len(extra_feeds),
        "unique_feed_urls": len(base_urls | set(extra_feeds)),
        "provider_status": get_provider_status(),
        "snapshot_visible_headlines": len(snap.headlines),
        "coverage_note": "Snapshot başlıkları sınırlı görünüm; keşif ve forecast ayrı 72 saatlik defter tutar.",
    }
    try:
        from packages.data.providers.news import article_enrichment
        from packages.discovery import news_discovery, news_forecast

        discovery_view = news_discovery.viewmodel(limit_events=0)
        forecast_view = news_forecast.viewmodel()
        news_consensus["processing"] = {
            "discovery": {
                "generated_at": discovery_view.get("generated_at"),
                "pool_headlines": (discovery_view.get("stats") or {}).get("pool"),
                "article_enriched": (discovery_view.get("stats") or {}).get("article_enriched", 0),
                "article_coverage": (discovery_view.get("stats") or {}).get("article_coverage"),
                "screened": (discovery_view.get("stats") or {}).get("screened", 0),
                "active_candidates": len(discovery_view.get("candidates") or []),
                "status": discovery_view.get("status"),
            },
            "forecast": {
                "generated_at": forecast_view.get("generated_at"),
                "ledger_headlines": forecast_view.get("headlines", 0),
                "asset_forecasts": len(forecast_view.get("forecasts") or []),
                "directional_forecasts": sum(
                    1 for row in (forecast_view.get("forecasts") or [])
                    if row.get("direction") in {"up", "down"}
                ),
                "mode": forecast_view.get("mode"),
            },
        }
        snapshot_coverage = article_enrichment.coverage(snap.headlines)
        pool_coverage = (discovery_view.get("stats") or {}).get("article_coverage") or {}
        effective_coverage = pool_coverage if pool_coverage.get("status") not in {None, "EMPTY", "UNAVAILABLE"} else snapshot_coverage
        news_consensus["article_coverage"] = {
            **effective_coverage,
            "coverage_basis": "discovery_pool" if effective_coverage is pool_coverage else "snapshot",
            "snapshot": snapshot_coverage,
            "discovery_pool": pool_coverage,
        }
    except Exception:
        news_consensus["processing"] = {"status": "unavailable"}
        news_consensus["article_coverage"] = {"status": "UNAVAILABLE"}
    # Build the operational read model once and feed the same snapshot into
    # both the CFO narrative and the dashboard cards.  Previously the premium
    # brief could only see world/news evidence, so it read like a headline
    # feed even when the decision engine had already identified the actual
    # blockers (confidence, timing, EV, stale data, or concentration).
    agent_brief = agent_brief_view(
        view, snap, ps, provenance, halt_active=halt_active
    )
    # Premium brief is a narrative-only overlay.  It returns immediately
    # with a deterministic summary and lets the optional LLM rewrite happen
    # in one background worker when the evidence digest changes.
    premium_brief = build_premium_brief(
        headlines=snap.headlines,
        world_brief=world_brief,
        news_consensus=news_consensus,
        world_state=world_state.to_dict(),
        causal_shadow=causal_shadow.to_dict(),
        portfolio_risk=portfolio_risk.to_dict(),
        risk_gate={"action": risk.action, "reason": risk.reason},
        dqs={"status": snap.quality.status, "score": snap.quality.score},
        agent_brief=agent_brief,
        decision_matrix=view,
    )
    return {
        "generated_at": view["generated_at"],
        "snapshot_id": getattr(snap, "id", None) or getattr(snap, "snapshot_id", None),
        "snapshot_generated_at": snap.generated_at.isoformat(),
        "paper_state_revision": getattr(ps, "revision", None),
        "mode": provenance,
        "engine": engine,
        "prices": prices,
        "headlines": headlines,
        "news_consensus": news_consensus,
        "decision_matrix": view,
        "paper_state": {
            "revision": ps.revision,
            "open_positions": [
                {
                    "id": position.id,
                    "symbol": position.symbol,
                    "side": position.side,
                    "timeframe": position.timeframe,
                    "size_usd": position.size_usd,
                    "unrealized_pnl_usd": round(position.unrealized_pnl_usd, 2),
                }
                for position in ps.open_positions
            ],
        },
        "agent_brief": agent_brief,
        "executive": executive,
        "decision_trace": decision_trace_view(view, snap),
        "world_state": world_state.to_dict(),
        "world_brief": world_brief,
        "premium_brief": premium_brief,
        "causal_shadow": causal_shadow.to_dict(),
        "portfolio_risk": portfolio_risk.to_dict(),
        # Haber kaynaklı hazırlıklar emir değildir; frontend'e durum, kanıt,
        # geçerlilik ve bekleyen kapıyı birlikte gösterir.
        "news_prepared_setups": [
            news_setup.view(item) for item in ps.news_prepared_setups[-32:]
        ],
    }


def _refresh_brief_cache() -> None:
    """Refresh the read-only cockpit cache without blocking HTTP requests."""
    global _BRIEF_CACHE, _BRIEF_REFRESHING
    try:
        result = _build_cockpit_brief()
        with _BRIEF_CACHE_LOCK:
            _BRIEF_CACHE = (time.monotonic(), result)
    except Exception:
        _log.exception("cockpit brief refresh failed; last good snapshot kept")
    finally:
        with _BRIEF_CACHE_LOCK:
            _BRIEF_REFRESHING = False


@router.get("/cockpit/brief")
def get_cockpit_brief() -> dict:
    """Return a cached read-only brief; refresh stale data in the background.

    Tick/learning workers may spend seconds in CPU-bound analysis. The first
    request still builds the same authoritative view, but subsequent dashboard
    polls never wait behind that work and keep the last known-good snapshot.
    """
    global _BRIEF_CACHE, _BRIEF_REFRESHING
    now = time.monotonic()
    with _BRIEF_CACHE_LOCK:
        cached = _BRIEF_CACHE
        if cached is not None:
            age = now - cached[0]
            if age <= _BRIEF_TTL_SEC:
                return cached[1]
            if not _BRIEF_REFRESHING:
                _BRIEF_REFRESHING = True
                threading.Thread(
                    target=_refresh_brief_cache,
                    name="cockpit-brief-refresh",
                    daemon=True,
                ).start()
            return cached[1]

    # Cold start only: preserve the original synchronous behaviour so the
    # endpoint never returns an empty/partial decision view.
    result = _build_cockpit_brief()
    with _BRIEF_CACHE_LOCK:
        _BRIEF_CACHE = (time.monotonic(), result)
    return result
