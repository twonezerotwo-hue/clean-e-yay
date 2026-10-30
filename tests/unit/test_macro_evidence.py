from datetime import UTC, datetime
from types import SimpleNamespace

from packages.macro.correlation import rolling_regime_correlation
from packages.macro.evidence import build_macro_evidence


def _snapshot(*, title="Hormuz blockade raises oil supply risk", source="official"):
    catalyst = SimpleNamespace(
        id="evt-1", title=title, title_tr=None, category="geopolitics",
        market_impact=None, source=source, ts=datetime(2026, 10, 29, tzinfo=UTC),
        actual=None, expected=None, previous=None, revised=None,
        verified=True, affected_assets=[],
    )
    tech = SimpleNamespace(direction_score=68.0, score=68.0, ema_stack="bullish", status="OK")
    return SimpleNamespace(
        catalysts=[catalyst], technicals={"BRENT": tech}, technicals_by_tf=None,
        ingested_at=datetime(2026, 10, 29, tzinfo=UTC),
    )


def test_macro_evidence_has_one_stable_identity_and_technical_status():
    rows = build_macro_evidence(_snapshot(), regime="RISK_OFF")
    assert len(rows) == 2  # the event maps to Brent and WTI
    assert rows[0]["evidence_id"].startswith("ev_")
    assert rows[0]["event_id"].startswith("evt_")
    assert rows[0]["source_id"] == "direct:official"
    assert rows[0]["correlation_regime"] == "RISK_OFF"
    assert rows[0]["technical_confirmation"] == "CONFIRMED"
    assert rows[0]["provenance"]["shadow_only"] is True


def test_missing_numeric_values_are_not_imputed():
    rows = build_macro_evidence(_snapshot(title="Fed central bank inflation statement", source="unknown"), regime="UNKNOWN")
    assert rows
    assert rows[0]["expected"] is None
    assert rows[0]["actual"] is None
    assert rows[0]["surprise"] is None


def test_news_and_technical_direction_are_joined_not_overwritten():
    rows = build_macro_evidence(_snapshot(title="Hormuz blockade raises oil supply risk"), regime="RISK_OFF")
    brent = next(row for row in rows if row["asset"] == "BRENT")
    assert brent["direction"] == "bullish"
    assert brent["technical_confirmation"] == "CONFIRMED"


def test_official_actual_and_calendar_expectation_share_one_event_id():
    snap = _snapshot(title="US CPI", source="bls_official")
    snap.catalysts[0].actual = 3.1
    snap.catalysts[0].expected = None
    snap.catalysts[0].unit = "percent"
    snap.catalysts[0].affected_assets = ["DXY"]
    shadow = SimpleNamespace(
        id="calendar-99", title="Consumer Price Index", title_tr=None,
        category="MACRO_WEB_SHADOW", market_impact="calendar consensus",
        source="investing_web_calendar", ts=datetime(2026, 11, 15, tzinfo=UTC),
        actual=None, expected=3.0, previous=2.9, revised=None,
        unit="percent", verified=False, affected_assets=[],
    )
    snap.macro_releases = []
    snap.catalysts.append(shadow)
    rows = build_macro_evidence(snap, regime="MIXED")
    assert len(rows) == 1
    assert rows[0]["actual"] == 3.1
    assert rows[0]["expected"] == 3.0
    assert "+" in rows[0]["source_id"]


def test_different_units_do_not_create_fake_surprise():
    snap = _snapshot(title="US CPI", source="bls_official")
    snap.catalysts[0].actual = 336.94
    snap.catalysts[0].unit = "index"
    snap.catalysts[0].affected_assets = ["DXY"]
    shadow = SimpleNamespace(
        id="calendar-percent", title="Consumer Price Index", title_tr=None,
        category="MACRO_WEB_SHADOW", market_impact="calendar consensus",
        source="investing_web_calendar", ts=snap.catalysts[0].ts,
        actual=None, expected=3.1, previous=3.0, revised=None,
        unit="percent", verified=False, affected_assets=[],
    )
    snap.catalysts.append(shadow)
    rows = build_macro_evidence(snap, regime="MIXED")
    # The index observation and percent expectation remain separate events;
    # neither row reports a fabricated 333-point surprise.
    assert len(rows) == 1
    assert any(row["unit"] == "index" and row["actual"] == 336.94 for row in rows)
    assert all(row["surprise"] is None for row in rows)


def test_rolling_regime_correlation_is_bounded_and_shadow_only():
    rows = rolling_regime_correlation([
        {"asset": "BRENT", "regime": "RISK_OFF", "timeframe": "1d", "direction": "bullish", "outcome_return": 0.02},
        {"asset": "BRENT", "regime": "RISK_OFF", "timeframe": "1d", "direction": "bullish", "outcome_return": -0.01},
        {"asset": "BRENT", "regime": "RISK_OFF", "timeframe": "1d", "direction": "bearish", "outcome_return": -0.03},
    ])
    assert rows[0]["n"] == 3
    assert 0 <= rows[0]["hit_rate"] <= 1
    assert rows[0]["shadow_only"] is True


def test_extended_macro_topics_are_canonical_and_keep_shadow_status():
    snap = _snapshot(title="ISM Manufacturing PMI beats expectations", source="investing_web_calendar")
    snap.catalysts[0].actual = 52.0
    snap.catalysts[0].expected = 50.0
    snap.catalysts[0].unit = "number"
    snap.catalysts[0].verified = False
    rows = build_macro_evidence(snap, regime="RISK_ON")
    assert rows
    assert rows[0]["verified"] is False
    assert rows[0]["event_id"].startswith("evt_")
    assert rows[0]["surprise"] == 2.0
