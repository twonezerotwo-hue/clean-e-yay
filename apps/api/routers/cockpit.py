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

from apps.api.routers.paper_trading import _serialize_state as serialize_paper_state
from packages.agent.brief_id import build_brief_id
from packages.agent.briefing import _engine_health as agent_engine_health
from packages.agent.briefing import build_executive
from packages.agent.llm.premium_brief import build_premium_brief
from packages.agent.llm.world_report import build_world_brief
from packages.agent.localization import localize_headline
from packages.causal.engine import build_shadow
from packages.data.provenance import data_provenance
from packages.data.providers.news import classify as news_classify
from packages.data.providers.news import get_provider_status
from packages.data.providers.news import rss as news_rss
from packages.data.providers.news.provenance import build_consensus
from packages.decision import agent_pipeline, read_model
from packages.decision.cockpit import (
    agent_brief_view,
    decision_trace_view,
)
from packages.learning import tf_weight_trainer
from packages.paper import news_setup
from packages.paper import ticket as paper_ticket
from packages.portfolio import build_portfolio_risk
from packages.risk import halt as halt_store
from packages.world_state.engine import build as build_world_state

router = APIRouter(tags=["cockpit"])

_log = logging.getLogger("api.cockpit")
_BRIEF_TTL_SEC = max(1.0, float(os.environ.get("COCKPIT_BRIEF_CACHE_SEC", "10")))
_BRIEF_CACHE: tuple[float, dict] | None = None
_BRIEF_CACHE_LOCK = threading.Lock()
_BRIEF_REFRESHING = False


def _build_cockpit_brief() -> dict:
    dv = read_model.current()
    snap, ps = dv.snap, dv.ps
    matrix_symbols, regime, risk, decisions = dv.symbols, dv.regime, dv.risk, dv.decisions
    view = dv.matrix()
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
            "article_summary": getattr(headline, "article_summary", None),
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
                "article_pending": (discovery_view.get("stats") or {}).get("article_pending", 0),
                "article_failed": (discovery_view.get("stats") or {}).get("article_failed", 0),
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
    # Canonical projections: the frontend hooks select these slices from this
    # envelope instead of fetching separate snapshots. Optional diagnostics
    # fail closed and never make the core brief unavailable.
    canonical_paper_state = serialize_paper_state(ps)
    canonical_tickets = paper_ticket.load_last()
    try:
        tf_weights = tf_weight_trainer.resolve_live_tf_weights()
    except Exception:
        tf_weights = None
    try:
        agent_views = agent_pipeline.build_agent_matrix(
            matrix_symbols, risk_action=risk.action, tf_weights=tf_weights
        )
        canonical_agent_matrix = agent_pipeline.matrix_viewmodel(
            agent_views, risk_action=risk.action
        )
        canonical_agent_matrix.update(
            {
                "source": "agent_shadow",
                "execution_authority": "observe_only",
                "snapshot_id": getattr(snap, "snapshot_id", None),
                "snapshot_generated_at": snap.generated_at.isoformat(),
                "paper_state_revision": ps.revision,
            }
        )
    except Exception:
        canonical_agent_matrix = {
            "risk_action": risk.action,
            "timeframes": [],
            "symbols": [],
            "source": "agent_shadow",
            "execution_authority": "observe_only",
            "snapshot_id": getattr(snap, "snapshot_id", None),
            "paper_state_revision": ps.revision,
            "error": "agent_matrix_unavailable",
        }
    brief_id = build_brief_id(
        getattr(snap, "id", None) or getattr(snap, "snapshot_id", None),
        getattr(ps, "revision", None),
    )
    # One identity envelope for every first-screen consumer.  Panels may
    # render different slices, but they must not invent a second snapshot or
    # silently merge another tick's evidence.
    evidence_ids = sorted({
        str(item.evidence_id)
        for item in ps.news_prepared_setups
        if getattr(item, "evidence_id", None)
    })
    decision_ids = sorted({
        str(item.decision_id)
        for item in decisions
        if getattr(item, "decision_id", None)
    })
    canonical_ids = {
        "schema_version": 1,
        "snapshot_id": getattr(snap, "id", None) or getattr(snap, "snapshot_id", None),
        "brief_id": brief_id,
        "paper_state_revision": getattr(ps, "revision", None),
        "decision_ids": decision_ids,
        "evidence_ids": evidence_ids,
        "generated_at": view["generated_at"],
    }
    # Additive identity: all renderers can now prove they read the same
    # snapshot/state pair.  Narrative contents remain unchanged.
    agent_brief = {**agent_brief, "brief_id": brief_id}
    executive = {**executive, "brief_id": brief_id}
    premium_brief = {**premium_brief, "brief_id": brief_id}
    return {
        "generated_at": view["generated_at"],
        "snapshot_id": getattr(snap, "id", None) or getattr(snap, "snapshot_id", None),
        "snapshot_generated_at": snap.generated_at.isoformat(),
        "paper_state_revision": getattr(ps, "revision", None),
        "brief_id": brief_id,
        "canonical_ids": canonical_ids,
        "mode": provenance,
        "engine": engine,
        "prices": prices,
        "headlines": headlines,
        "news_consensus": news_consensus,
        "decision_matrix": view,
        "paper_state": canonical_paper_state,
        "trade_tickets": canonical_tickets,
        "agent_matrix": canonical_agent_matrix,
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


@router.get("/cockpit/state")
def get_cockpit_state() -> dict:
    """Canonical cockpit read model.

    ``/cockpit/brief`` remains as a backwards-compatible alias.  New clients
    use this route so Brain, Heart, Soul and Conscious can consume one
    snapshot/decision/brief envelope instead of merging independent polls.
    The route is read-only and intentionally shares the exact cache and
    builder; it cannot create a second decision path.
    """
    return get_cockpit_brief()
