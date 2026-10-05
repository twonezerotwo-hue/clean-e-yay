"""Haber istihbaratı → YZ yorumları (persona raporları, sohbet bağlamı, Brain) — ağsız."""
from __future__ import annotations

from packages.agent import briefing
from packages.agent.llm import report
from packages.discovery import ideas, intel, news_discovery, news_forecast

CELLS = [
    {"symbol": "BTCUSD", "timeframe": "1h", "candidate_action": "open_long", "action": "hold", "score": 62},
    {"symbol": "XAUUSD", "timeframe": "1d", "candidate_action": "open_long", "action": "open_long", "score": 66},
]
FORECASTS = {
    "BTCUSD": {"symbol": "BTCUSD", "direction": "down", "strength": 57, "n_headlines": 3,
               "evidence": [{"title": "Exchange hack drains reserves", "origin": "llm"}]},
    "XAUUSD": {"symbol": "XAUUSD", "direction": "up", "strength": 33, "n_headlines": 2,
               "evidence": [{"title": "Gold demand rises", "origin": "rss"}]},
    "FCX": {"symbol": "FCX", "direction": "up", "strength": 60},              # kayıt dışı → registry listesinde yok
}
REVIEW = [{"symbol": "FCX", "name": "Freeport-McMoRan Inc.", "chain": "Chile mine strike → Bakır arzı daralır",
           "mechanism": "arz kesintisi", "technical": "1h sinyal, R/Ö 2.0", "ai_verdict": "İZLE", "score": 61,
           "news_strength": 60, "notified_at": "2026-10-05T12:00:00+00:00"}]
EVENTS = {"events": [{"title": "Chile copper mine strike halts output", "consequence": "Bakır arzı daralır",
                      "assets": [{"symbol": "FCX", "direction": "up", "status": "valid"},
                                 {"symbol": "XAUUSD", "direction": "up", "status": "registry"},
                                 {"symbol": "TNTA", "direction": "up", "status": "rejected"}]}]}


def _patch(monkeypatch):
    monkeypatch.setattr(news_forecast, "load_forecasts", lambda: FORECASTS)
    monkeypatch.setattr("packages.data.registry.assets.trade_symbols", lambda: ["BTCUSD", "XAUUSD"])
    monkeypatch.setattr(news_discovery, "viewmodel", lambda limit_events=12: EVENTS)
    monkeypatch.setattr(ideas, "review_recommendations", lambda max_age=None: REVIEW)
    monkeypatch.setattr(ideas, "compact_for_chat", lambda limit=3: {"top": [{"symbol": "FCX", "score": 61}]})


def test_context_section_is_quantized_evidence_not_decision(monkeypatch):
    _patch(monkeypatch)
    ni = intel.compact_for_context(CELLS)
    assert "KANITTIR, karar değildir" in ni["note"] and ni["shadow_scorecard"]["affect_decision"] is False
    assert [(f["symbol"], f["strength"], f["via_ai_chain"]) for f in ni["registry_forecasts"]] == [
        ("BTCUSD", 50, True), ("XAUUSD", 30, False)]                       # 10'luk kova, kayıt dışı yok
    assert ni["decision_check"][0] == {"symbol": "BTCUSD", "timeframe": "1h", "side": "long", "final_action": "hold",
                                       "forecast": "down", "relation": "conflict", "strength": 50,
                                       "evidence": "Exchange hack drains reserves"}
    assert ni["discovery_chains"] == [{"headline": "Chile copper mine strike halts output",
                                       "consequence": "Bakır arzı daralır", "assets": ["FCX↑", "XAUUSD↑ (takipte)"]}]
    assert ni["review_recommendations"][0]["symbol"] == "FCX" and ni["top_ideas"][0]["symbol"] == "FCX"


def _ctx(ni):
    return {"snapshot_id": "s1", "dqs": {"status": "OK"}, "technical_gate": [], "deep_data": {},
            "matrix": {"top_cells": [], "risk_gate": {"action": "HOLD", "reason": "ok"}, "blocked_by_reasons": [],
                       "regime": "NEUTRAL"},
            "halt": {"active": False, "events": []}, "correlation_clusters": [], "news": [], "catalysts": [],
            "paper": {"daily_pnl_usd": 0.0}, "news_intel": ni}


def test_personas_cite_news_intel_from_code(monkeypatch):
    _patch(monkeypatch)
    ctx = _ctx(intel.compact_for_context(CELLS))
    analyst = report._evidence_for("analyst", ctx)
    assert "news_check:BTCUSD:1h long × haber down(50) conflict" in analyst
    assert any(e.startswith("review:FCX") for e in analyst)
    risk = report._evidence_for("risk_officer", ctx)
    assert "news_conflict:BTCUSD:1h long × haber down(50)" in risk
    macro = report._evidence_for("macro_strategist", ctx)
    assert "news_forecast:BTCUSD down(50)" in macro and any(e.startswith("news_chain:Chile") for e in macro)
    concerns = report._fallback_concerns("risk_officer", ctx)
    assert any("çelişiyor" in c and "gölge" in c for c in concerns)
    assert "decision_check" in report._PERSONA_BRIEFS["analyst"]


def test_brain_briefing_lists_review_and_conflict(monkeypatch):
    _patch(monkeypatch)
    heads = briefing._intel_headlines(CELLS)
    assert heads[0].title.startswith("İnceleme tavsiyesi: FCX") and "İşlem önerisi değildir" in heads[0].detail
    assert heads[1].tone == "warn" and "çelişiyor" in heads[1].title and "güç 57" in heads[1].title


def test_context_degrades_safely(monkeypatch):
    monkeypatch.setattr(news_forecast, "load_forecasts", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    from packages.agent.llm import context

    assert context._news_intel(CELLS) == intel.empty()
    assert briefing._intel_headlines(CELLS) == []
