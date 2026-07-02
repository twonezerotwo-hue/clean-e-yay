"""Consensus haber modülü — sembol-ilişkili skorlama (news_symbol_filter).

Politika:
- Flag KAPALI (default) → legacy global sentiment tally birebir korunur;
  symbol argümanı davranışı DEĞİŞTİRMEZ.
- Flag AÇIK → yalnız o sembole `asset_impact` taşıyan VERIFIED başlıklar
  sayılır (DATA_POLICY: verified=False consensus'a girmez). Yön global
  sentiment yerine sembole özgü impact değerinden gelir. İlgili başlık
  yoksa 50 (nötr) — alakasız küresel haber sembol skorunu oynatamaz.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.types import NewsHeadline


def _headline(
    hid: str,
    title: str,
    sentiment: str,
    asset_impact: dict[str, float],
    *,
    verified: bool = True,
) -> NewsHeadline:
    return NewsHeadline(
        id=hid,
        source="test",
        ts=datetime.now(UTC),
        title=title,
        sentiment=sentiment,
        asset_impact=asset_impact,
        verified=verified,
    )


def _snap(headlines: list[NewsHeadline]) -> SimpleNamespace:
    # _news yalnız .headlines okur — minimal stub yeterli (network yok).
    return SimpleNamespace(headlines=headlines)


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(
        ce, "load_thresholds", lambda: {"consensus": {"news_symbol_filter": True}}
    )


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setattr(
        ce, "load_thresholds", lambda: {"consensus": {"news_symbol_filter": False}}
    )


def test_flag_off_keeps_legacy_global_tally(flag_off) -> None:
    """Flag kapalı → symbol verilse bile eski global tally birebir."""
    snap = _snap([
        _headline("h1", "Bitcoin rally", "bullish", {"BTCUSD": 1.0}),
        _headline("h2", "Gold falls", "bearish", {"XAUUSD": -1.0}),
        _headline("h3", "Markets mixed", "neutral", {}),
    ])
    # (1 bullish - 1 bearish) / 3 * 25 = 0 → 50.0; symbol argümanı etkisiz.
    assert ce._news(snap, "XAGUSD") == 50.0
    assert ce._news(snap) == 50.0


def test_flag_on_scores_only_symbol_relevant_headlines(flag_on) -> None:
    """BTC haberi XAGUSD skorunu OYNATMAZ; BTCUSD skorunu oynatır."""
    snap = _snap([
        _headline("h1", "Bitcoin rally", "bullish", {"BTCUSD": 1.0}),
        _headline("h2", "Bitcoin adoption grows", "bullish", {"BTCUSD": 1.0}),
    ])
    assert ce._news(snap, "BTCUSD") == 75.0   # mean(+1, +1) × 25 + 50
    assert ce._news(snap, "XAGUSD") == 50.0   # ilgili başlık yok → nötr


def test_flag_on_direction_from_asset_impact_not_sentiment(flag_on) -> None:
    """Hawkish Fed haberi: sentiment bearish ama DXY impact +1 → DXY > 50."""
    snap = _snap([
        _headline("h1", "Fed signals rate hike", "bearish", {"DXY": 1.0}),
    ])
    assert ce._news(snap, "DXY") == 75.0


def test_flag_on_unverified_headlines_excluded(flag_on) -> None:
    """DATA_POLICY — verified=False başlık, impact eşleşse bile sayılmaz."""
    snap = _snap([
        _headline("h1", "Bitcoin rally", "bullish", {"BTCUSD": 1.0}, verified=False),
    ])
    assert ce._news(snap, "BTCUSD") == 50.0


def test_flag_on_mixed_impacts_average(flag_on) -> None:
    snap = _snap([
        _headline("h1", "Gold surges on war fears", "bullish", {"XAUUSD": 1.0}),
        _headline("h2", "Gold retreats", "bearish", {"XAUUSD": -1.0}),
        _headline("h3", "Ceasefire talks", "bullish", {"XAUUSD": -1.0, "BRENT": -1.0}),
    ])
    # XAUUSD: mean(+1, -1, -1) = -1/3 → 50 - 25/3 ≈ 41.667
    assert ce._news(snap, "XAUUSD") == pytest.approx(50.0 - 25.0 / 3.0)
    # BRENT: mean(-1) → 25.0
    assert ce._news(snap, "BRENT") == 25.0


def test_flag_on_no_headlines_neutral(flag_on) -> None:
    assert ce._news(_snap([]), "BTCUSD") == 50.0
