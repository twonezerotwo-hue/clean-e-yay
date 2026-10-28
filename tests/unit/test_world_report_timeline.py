"""World brief'in haber olay zinciri sunumu için regresyon testleri."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from packages.agent.llm import world_report


def test_timeline_preserves_prior_peace_signal_and_later_reversal(tmp_path, monkeypatch):
    path = tmp_path / "news_event_ledger.jsonl"
    rows = [
        {
            "id": "peace-1",
            "source": "Reuters",
            "title": "After election, peace talks could end the war",
            "sentiment": "bullish",
            "ts": "2026-10-21T12:00:00+00:00",
            "symbols": {"XAUUSD": 1},
        },
        {
            "id": "reversal-1",
            "source": "AP",
            "title": "Senate warns the war may continue despite the talks",
            "sentiment": "bearish",
            "ts": "2026-10-22T08:00:00+00:00",
            "symbols": {"XAUUSD": -1},
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setenv("NEWS_EVENT_LEDGER_PATH", str(path))

    timeline = world_report._event_timeline(
        [], now=datetime(2026, 10, 22, 12, 0, tzinfo=UTC), limit=18
    )

    assert {row["id"] for row in timeline} == {"peace-1", "reversal-1"}
    assert {row["phase"] for row in timeline} == {"PEACE_SIGNAL", "REVERSAL_OR_ESCALATION"}
    summary = world_report._timeline_summary(timeline)
    assert "barış" in summary.lower()
    assert "karşı" in summary.lower()


def test_timeline_does_not_invent_price_reaction_without_price_evidence():
    summary = world_report._timeline_summary([
        {
            "phase": "PEACE_SIGNAL",
            "ts": "2026-10-21T12:00:00+00:00",
        },
        {
            "phase": "REVERSAL_OR_ESCALATION",
            "ts": "2026-10-22T08:00:00+00:00",
        },
    ])
    assert "fiyat tepkisi" in summary.lower()
    assert "yükseldi" not in summary.lower()
    assert "çakıldı" not in summary.lower()


def test_actor_statement_without_ticker_mapping_is_kept(tmp_path, monkeypatch):
    path = tmp_path / "news_forecast.json"
    path.write_text(
        json.dumps({
            "headlines": {
                "senate-1": {
                    "title": "Senate statement says the war may continue",
                    "source": "AP",
                    "ts": "2026-10-22T08:00:00+00:00",
                    "impact": {},
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEWS_FORECAST_PATH", str(path))
    monkeypatch.setenv("NEWS_EVENT_LEDGER_PATH", str(tmp_path / "missing.jsonl"))

    timeline = world_report._event_timeline(
        [], now=datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    )

    assert timeline and timeline[0]["source"] == "AP"
    assert timeline[0]["phase"] == "REVERSAL_OR_ESCALATION"


def test_market_selloff_is_classified_as_reversal():
    phase, label = world_report._timeline_phase(
        "Market sell-off gains steam as concerns about Iran war and high AI spending collide"
    )

    assert phase == "REVERSAL_OR_ESCALATION"
    assert label == "Karşı açıklama / gerilim"


def test_business_deal_is_not_classified_as_peace():
    phase, _ = world_report._timeline_phase(
        "Fortescue warns of production slowdown without China deal"
    )

    assert phase == "NEWS"
