from __future__ import annotations

import packages.agent.llm.premium_brief as premium


def _world(title: str = "Senate açıklaması") -> dict:
    return {
        "summary": "Haber etkisi izleniyor.",
        "timeline_summary": "Barış sinyali ardından karşı açıklama geldi.",
        "event_timeline": [
            {
                "id": "timeline-1",
                "ts": "2026-10-22T10:00:00+00:00",
                "source": "Test Wire",
                "title": title,
                "phase": "REVERSAL_OR_ESCALATION",
                "phase_label": "Karşı açıklama / gerilim",
                "asset_impact": {"XAUUSD": "up"},
            }
        ],
        "affected_assets": ["XAUUSD"],
    }


def _reset() -> None:
    with premium._LOCK:
        premium._LAST_DIGEST = None
        premium._LAST_AI_DIGEST = None
        premium._LAST_AI_RESULT = None
        premium._AI_FUTURE = None
        premium._AI_FUTURE_DIGEST = None
        premium._LAST_SIGNIFICANT_KEYS = set()


def test_premium_brief_emits_alert_only_on_new_evidence(monkeypatch):
    _reset()
    def submit_done(**_):
        future = premium.Future()
        future.set_result({"source": "fallback", "summary": "kısa"})
        return future

    monkeypatch.setattr(premium, "_submit_ai", submit_done)
    first = premium.build_premium_brief(
        headlines=[{"id": "h1", "source": "Wire", "title": "Barış açıklaması", "ts": "2026-10-22T10:00:00+00:00"}],
        world_brief=_world(),
        news_consensus={},
    )
    second = premium.build_premium_brief(
        headlines=[{"id": "h1", "source": "Wire", "title": "Barış açıklaması", "ts": "2026-10-22T10:00:00+00:00"}],
        world_brief=_world(),
        news_consensus={},
    )
    assert first["mode"] == "DELTA"
    assert first["alert"] is None
    assert second["mode"] == "STEADY"
    assert second["alert"] is None
    changed_world = _world("Yeni karşı açıklama")
    changed_world["event_timeline"][0]["id"] = "timeline-2"
    third = premium.build_premium_brief(
        headlines=[{"id": "h2", "source": "Wire", "title": "Yeni açıklama", "ts": "2026-10-22T10:05:00+00:00"}],
        world_brief=changed_world,
        news_consensus={},
    )
    assert third["mode"] == "ALERT"
    assert third["alert"]


def test_premium_brief_uses_ai_result_when_ready(monkeypatch):
    _reset()
    monkeypatch.setattr(
        premium,
        "_submit_ai",
        lambda **_: premium.Future(),
    )
    digest = premium._digest(
        headlines=(), world_brief=_world(), news_consensus={}
    )
    with premium._LOCK:
        premium._LAST_DIGEST = digest
        premium._LAST_AI_DIGEST = digest
        premium._LAST_AI_RESULT = {"source": "llm", "summary": "AI'nin kısa raporu", "what_to_watch": ["Teyit"]}
    result = premium.build_premium_brief(
        headlines=[],
        world_brief=_world(),
        news_consensus={},
    )
    assert result["report"] == "AI'nin kısa raporu"
    assert result["ai"]["status"] == "READY"


def test_old_escalation_row_does_not_alert_for_unrelated_new_headline(monkeypatch):
    _reset()

    def submit_done(**_):
        future = premium.Future()
        future.set_result({"source": "fallback", "summary": "kısa"})
        return future

    monkeypatch.setattr(premium, "_submit_ai", submit_done)
    base = {"id": "h1", "source": "Wire", "title": "İlk haber", "ts": "2026-10-22T10:00:00+00:00"}
    premium.build_premium_brief(headlines=[base], world_brief=_world(), news_consensus={})
    next_row = {**base, "id": "h2", "title": "Yeni ama sıradan haber"}
    result = premium.build_premium_brief(
        headlines=[base, next_row], world_brief=_world(), news_consensus={}
    )
    assert result["mode"] == "DELTA"
    assert result["alert"] is None


def test_premium_brief_is_one_cfo_narrative(monkeypatch):
    _reset()
    monkeypatch.setattr(premium, "_submit_ai", lambda **_: premium.Future())
    result = premium.build_premium_brief(
        headlines=[
            {
                "id": "h1",
                "source": "Reuters",
                "title": "Ceasefire talks resume",
                "ts": "2026-10-22T10:05:00+00:00",
                "verified": True,
            }
        ],
        world_brief=_world("Senate açıklaması"),
        news_consensus={
            "assets": [{"symbol": "XAUUSD", "conflict": True}],
            "story_count": 2,
            "independent_source_families": 2,
        },
    )
    assert "Güncel gelişmeler:" in result["report"]
    assert "Yönetim kararı:" in result["report"]
    assert "Haber özeti:" not in result["report"]
    assert "graph_no_entity_match" not in result["report"]


def test_premium_brief_explains_no_trade_and_empty_discovery(monkeypatch):
    _reset()
    monkeypatch.setattr(premium, "_submit_ai", lambda **_: premium.Future())
    result = premium.build_premium_brief(
        headlines=[],
        world_brief=_world(),
        news_consensus={"idea_board": {"ideas": 0}},
        agent_brief={
            "open_paper_positions": 0,
            "top_blockers": ["confidence_floor", "entry_quality_v2:reversal_risk"],
            "top_candidates": [
                {
                    "symbol": "BRENT",
                    "timeframe": "1d",
                    "direction": "bullish",
                    "score": 60.2,
                    "execution_ready": False,
                }
            ],
        },
    )
    assert "Şu anda işlem açmıyorum" in result["report"]
    assert "En yakın aday Brent petrol" in result["report"]
    assert "Yeni varlık adayı yok" in result["report"]
    assert "confidence_floor" not in result["report"]


def test_premium_brief_prioritizes_market_shock_and_hides_internal_watch():
    developments = premium._latest_developments(
        headlines=[
            {
                "id": "quiet",
                "source": "Crypto Blog",
                "title": "New token launches after community vote",
                "ts": "2026-10-22T15:00:00+00:00",
            },
            {
                "id": "shock",
                "source": "NBC News",
                "title": "Market sell-off gains steam as AI funding slowdown collides with Iran war",
                "ts": "2026-10-22T14:00:00+00:00",
            },
        ],
        world_brief={"event_timeline": []},
        limit=1,
    )
    # Visible output is localized, while the high-impact row is still the
    # selected source (the quiet crypto headline must not displace it).
    assert developments.startswith("NBC News:")

    assert premium._clean_watch_items(
        ["baseline_supply", "graph_no_entity_match:abc", "Yeni resmi açıklama"]
    ) == ["Yeni resmi açıklama"]


def test_premium_brief_explains_joint_geopolitical_and_ai_shock():
    report = premium._cfo_report(
        headlines=[
            {
                "source": "World Wire",
                "title": "Market sell-off gains steam as concerns about Iran war and high AI spending collide",
                "ts": "2026-10-22T15:09:46+00:00",
            },
            {
                "source": "AP",
                "title": "Iran says tankers attacked in the Strait of Hormuz",
                "ts": "2026-10-22T15:00:00+00:00",
            },
        ],
        world_brief={"event_timeline": [], "timeline_summary": "Gerilim haberleri izleniyor."},
        consensus="Kaynaklar karışık.",
        conclusion="Fiyat teyidi bekleniyor.",
        conflicts=[],
        assets=["BRENT", "SP500", "BTCUSD"],
        watch=["Yeni resmi teyit"],
    )
    assert "Piyasa görünümü: İran savaşı/Hormuz" in report
    assert "İran savaşı/Hormuz" in report
    assert "Aktörler:" in report


def test_market_move_text_omits_missing_cache(monkeypatch):
    class EmptyCache:
        @staticmethod
        def load(_symbol, _timeframe):
            return None

    monkeypatch.setitem(__import__("sys").modules, "packages.data.providers.ohlcv.cache", EmptyCache)
    assert premium._market_move_text() is None


def test_unrelated_evidence_is_not_shown_over_market_shock():
    report = premium._cfo_report(
        headlines=[
            {
                "source": "NBC",
                "title": "Market sell-off gains steam as concerns about Iran war and high AI spending collide",
                "ts": "2026-10-22T15:09:46+00:00",
            }
        ],
        world_brief={
            "summary": "Central bank policy evidence was found.",
            "event_timeline": [],
            "timeline_summary": "Gerilim haberleri izleniyor.",
        },
        consensus="Kaynaklar karışık.",
        conclusion="Fiyat teyidi bekleniyor.",
        conflicts=[],
        assets=["SP500"],
        watch=[],
    )
    assert "Kanıt: Merkez bankası" not in report
    assert "Piyasa görünümü: İran savaşı/Hormuz" in report


def test_repeated_equity_headlines_are_collapsed():
    developments = premium._latest_developments(
        headlines=[
            {"source": "CNBC", "title": "Nasdaq falls as AI spending and oil rise", "ts": "2026-10-22T15:00:00+00:00"},
            {"source": "Reuters", "title": "Wall Street sinks as Nasdaq falls over 2% on AI cost worries", "ts": "2026-10-22T14:59:00+00:00"},
            {"source": "AP", "title": "Iran says 7 oil tankers attacked in the Strait of Hormuz", "ts": "2026-10-22T14:58:00+00:00"},
        ],
        world_brief={"event_timeline": []},
        limit=4,
    )
    assert developments.count("Nasdaq") == 1
