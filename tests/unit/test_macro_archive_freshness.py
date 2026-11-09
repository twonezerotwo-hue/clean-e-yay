"""Makro arşiv tazeliği (9 Kasım 2026 bulgusu: US10Y 10 Temmuz'da dondu).

- Seriler tarihle eşlenir; bayat seri güncel seriyle birleşemez.
- Bayat arşiv: temel modül oy dışı (v2 yedeğine düşmez), rejim Likidite düşer,
  snapshot uyarısı çıkar.
- Bekçi: derinliği görülmüş seri de bayatlayınca güncellenir; oluşan bar yazılmaz.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.ingestion import pipeline
from packages.data.providers.ohlcv import history, yfinance
from packages.data.providers.rotation import flow, macro_liquidity
from packages.data.types import OHLCVBar
from packages.learning import macro_backfill as mbf
from packages.regime import classifier as rc
from packages.regime.classifier import RegimeLayer, RegimeOutput

N = 420


def _wave(base: float, amp: float, period: float) -> list[float]:
    return [base + amp * math.sin(i / period) + amp * 0.2 * math.sin(i * 0.71) for i in range(N)]


def _bar(sym: str, ts: datetime, close: float) -> OHLCVBar:
    return OHLCVBar(
        symbol=sym, timeframe="1d", ts=ts, open=close, high=close, low=close, close=close,
        volume=0.0, source="test", verified=True,
    )


def _day(days_ago: int, hour: int = 0) -> datetime:
    return datetime.now(UTC).replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))
    macro_liquidity._MEMO["key"] = None
    mbf._MEMO["ok"] = set()
    mbf._MEMO["last_attempt"] = 0.0

    def _write(sym: str, closes: list[float], end_days_ago: int = 1) -> None:
        n = len(closes)
        bars = [_bar(sym, _day(end_days_ago + n - 1 - i), c) for i, c in enumerate(closes)]
        (tmp_path / f"{sym}_1d.jsonl").write_text(
            "\n".join(json.dumps(b.model_dump(mode="json")) for b in bars), encoding="utf-8"
        )

    return _write


def _macro(archive, us10y_end_days_ago: int) -> None:
    archive("DXY", _wave(100.0, 3.0, 17.0))
    archive("US10Y", _wave(4.0, 0.4, 23.0), end_days_ago=us10y_end_days_ago)


def test_align_uses_only_common_dates():
    d1, d2, d3 = (datetime(2026, 11, day, tzinfo=UTC) for day in (3, 4, 5))
    a = [_bar("A", d1, 1.0), _bar("A", d2, 2.0), _bar("A", d3, 3.0)]
    b = [_bar("B", d1.replace(hour=12), 10.0), _bar("B", d3.replace(hour=12), 30.0)]
    assert flow.align_closes_by_date(a, b) == ([1.0, 3.0], [10.0, 30.0], date(2026, 11, 5))
    assert flow.align_closes_by_date(a, []) == ([], [], None)


def test_fresh_archive_scores_on_common_dates(archive):
    _macro(archive, us10y_end_days_ago=2)  # US10Y bir gün geride: son ortak gün o gün
    reading = macro_liquidity.read()
    assert reading.status == macro_liquidity.OK
    assert reading.as_of == _day(2).date()
    dxy = _wave(100.0, 3.0, 17.0)[:-1]
    assert reading.score == flow.liquidity_momentum_score(dxy, _wave(4.0, 0.4, 23.0))


def test_frozen_series_is_stale_not_scored(archive):
    _macro(archive, us10y_end_days_ago=122)
    reading = macro_liquidity.read()
    assert reading.status == macro_liquidity.STALE
    assert reading.score is None and reading.as_of == _day(122).date()


def test_age_limit_is_inclusive(archive):
    _macro(archive, us10y_end_days_ago=macro_liquidity.MAX_AGE_DAYS)
    assert macro_liquidity.read().status == macro_liquidity.OK
    macro_liquidity._MEMO["key"] = None
    _macro(archive, us10y_end_days_ago=macro_liquidity.MAX_AGE_DAYS + 1)
    assert macro_liquidity.read().status == macro_liquidity.STALE


def _snap():
    tech = SimpleNamespace(direction_score=60.0, status="OK", timeframe="1d", score=60.0)
    return SimpleNamespace(
        technicals_by_tf={"BTCUSD": {"1d": tech}}, technicals={}, headlines=[],
        rotation=SimpleNamespace(score=50.0, direction="neutral", evidence=[], status="OK"),
        volatility={}, derivatives={}, options={},
    )


def _regime():
    return RegimeOutput(
        label="NEUTRAL",
        layers=[
            RegimeLayer(name="Likidite", score=90.0, direction="bullish", evidence=[]),
            RegimeLayer(name="Sermaye Rotasyonu", score=80.0, direction="risk_on", evidence=[]),
            RegimeLayer(name="Risk İştahı", score=60.0, direction="neutral", evidence=[]),
        ],
    )


def test_consensus_drops_fundamental_without_v2_fallback(archive):
    _macro(archive, us10y_end_days_ago=122)
    res = ce.build("BTCUSD", _snap(), _regime(), "1d")
    assert "fundamental" not in {m.name for m in res.modules}
    assert "fundamental_dropped:stale_macro_archive:BTCUSD:1d" in res.warnings
    assert not any(w.startswith("fundamental_fallback") for w in res.warnings)
    assert not any(w.startswith("coverage_gate:forced_neutral:reason=missing_module") for w in res.warnings)


def test_regime_liquidity_layer_drops_when_stale(archive):
    _macro(archive, us10y_end_days_ago=122)
    snap = SimpleNamespace(
        prices=[SimpleNamespace(symbol="DXY", price=104.0), SimpleNamespace(symbol="US10Y", price=4.3),
                SimpleNamespace(symbol="VIX", price=20.0)],
        technicals={}, rotation=SimpleNamespace(score=50.0, direction="neutral", evidence=[], status="OK"),
    )
    assert rc._liquidity_layer(snap) is None
    assert "Likidite" in rc.classify(snap, stateful=False).dropped


def test_snapshot_warning_names_last_common_day(archive):
    _macro(archive, us10y_end_days_ago=122)
    assert pipeline._macro_archive_stale_warning() == (
        f"macro_archive_stale: DXY/US10Y son ortak gün {_day(122).date()}"
    )
    macro_liquidity._MEMO["key"] = None
    _macro(archive, us10y_end_days_ago=1)
    assert pipeline._macro_archive_stale_warning() is None


def test_archive_only_series_have_no_live_bar_path():
    assert not mbf.ARCHIVE_ONLY_DAILY & set(yfinance._SYMBOL_MAP)
    assert {"US10Y", "US05Y", "MOVE"} <= mbf.ARCHIVE_ONLY_DAILY


@pytest.mark.parametrize(
    ("last", "today", "stale"),
    [
        (date(2026, 11, 6), date(2026, 11, 9), False),  # Cuma barı, Pazartesi sabahı
        (date(2026, 11, 5), date(2026, 11, 9), True),   # Cuma kapanışı eksik
        (date(2026, 11, 6), date(2026, 11, 7), False),  # Cumartesi
        (date(2026, 11, 6), date(2026, 11, 10), True),  # Pazartesi kapanışı eksik
    ],
)
def test_daily_staleness_expects_last_weekday(archive, last, today, stale):
    path = history._path("US10Y", "1d")
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime(last.year, last.month, last.day, tzinfo=UTC)
    path.write_text(json.dumps(_bar("US10Y", ts, 4.0).model_dump(mode="json")), encoding="utf-8")
    assert mbf._is_stale("US10Y", today) is stale


def test_live_path_symbol_is_never_refreshed_here(archive):
    archive("DXY", [100.0] * 10, end_days_ago=40)
    assert mbf._is_stale("DXY", _day(0).date()) is False


def test_monthly_cpi_threshold(archive):
    archive("CPI", [300.0], end_days_ago=mbf.MONTHLY_MAX_AGE_DAYS)
    assert mbf._is_stale("CPI", _day(0).date()) is False
    archive("CPI", [300.0], end_days_ago=mbf.MONTHLY_MAX_AGE_DAYS + 1)
    assert mbf._is_stale("CPI", _day(0).date()) is True


def _all_deep(archive) -> None:
    for sym in mbf.BACKFILL_TICKERS:
        archive(sym, [100.0] * 450)


def test_deep_but_stale_series_is_refreshed_even_after_memo(archive, monkeypatch):
    """Kök hata: derinlik memo'su diziyi bir daha bakılmaz yapıyordu."""
    _all_deep(archive)
    monkeypatch.setattr(mbf, "_fetch", lambda *a, **k: pytest.fail("taze — fetch OLMAMALI"))
    assert mbf.ensure_depth()["status"] == "DEEP"
    assert "US10Y" in mbf._MEMO["ok"]

    archive("US10Y", [4.0] * 450, end_days_ago=120)  # memo'da iken dondu
    fresh = [_bar("US10Y", _day(i), 4.5) for i in range(1, 150)] + [_bar("US10Y", _day(0, 12), 9.9)]
    monkeypatch.setattr(mbf, "_fetch", lambda t, s, r: fresh if s == "US10Y" else [])
    out = mbf.ensure_depth()
    assert out["status"] == "FILLED" and out["filled"][0].startswith("US10Y:450->")
    bars = history.load("US10Y", "1d")
    assert bars[-1].ts.date() == _day(1).date()  # bugünün oluşan barı arşive GİRMEDİ
    assert all(b.close != 9.9 for b in bars)
    assert mbf.ensure_depth()["status"] == "DEEP"


def test_no_new_bars_is_not_a_failure(archive, monkeypatch):
    _all_deep(archive)
    archive("MOVE", [70.0] * 450, end_days_ago=10)
    existing = history.load("MOVE", "1d")
    monkeypatch.setattr(mbf, "_fetch", lambda t, s, r: existing)
    out = mbf.ensure_depth()
    assert out["status"] == "NO_NEW_BARS" and out["unchanged"] == ["MOVE"] and out["failed"] == []
    assert mbf.ensure_depth()["status"] == "RETRY_WAIT"


def test_fetch_keeps_internal_symbol_and_plan(monkeypatch):
    plan_before = dict(yfinance._TF_PLAN)
    bar = _bar("^TNX", _day(1), 4.5)
    monkeypatch.setattr(yfinance, "fetch_chart", lambda ticker, rng: ({}, [bar]))
    assert mbf._fetch("^TNX", "US10Y", "5y")[0].symbol == "US10Y"
    assert yfinance._TF_PLAN == plan_before
    monkeypatch.setattr(yfinance, "fetch_chart", lambda ticker, rng: None)
    assert mbf._fetch("^TNX", "US10Y", "5y") == []
