"""Takvim biriminde türetilmiş resmî gerçekleşen: dönüşüm, bayrak, eşleştirme kuralları."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from packages.data.providers.macro import derived
from packages.data.types import Catalyst
from packages.macro.evidence import build_macro_evidence
from packages.world_state.engine import build


def _months(values, start=(2025, 8)):
    year, month = start
    out = []
    for value in values:
        out.append(SimpleNamespace(ts=datetime(year, month, 1, tzinfo=UTC), close=value))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


def _derived_cpi(actual=0.3):
    return Catalyst(id="FRED_DERIVED_CPI_MOM:2026-09-30", ts=datetime(2026, 9, 30, 12, tzinfo=UTC), title="US CPI (MoM)",
                    source=derived.SOURCE, verified=True, actual=actual, unit="percent", region="US",
                    historical_surprise_volatility=0.2)


def _calendar(title="CPI (MoM)", day=14, month=10, actual=0.3, expected=0.2):
    return Catalyst(id=f"cal-{title}-{month}-{day}", ts=datetime(2026, month, day, 12, 30, tzinfo=UTC), title=title,
                    source="investing_web_calendar", verified=False, actual=actual, expected=expected,
                    unit="percent", region="United States", category="MACRO_WEB_SHADOW")


@pytest.mark.parametrize(("title", "want"), [
    ("CPI (MoM)", "mom"), ("Core CPI (YoY)", "yoy"), ("GDP (QoQ)", "qoq"), ("Nonfarm Payrolls", None),
    ("US Core PCE Price Index (MoM)", "mom"),
])
def test_measure_of(title, want):
    assert derived.measure_of(title) == want


def test_transforms():
    idx = [100.0 + i for i in range(14)]
    assert derived._transform(idx, "mom", 1.0) == round((113 / 112 - 1) * 100, 1)
    assert derived._transform(idx, "yoy", 1.0) == round((113 / 101 - 1) * 100, 1)
    assert derived._transform([159_000.0, 159_254.0], "diff", 1000.0) == 254_000.0
    assert derived._transform([7443.0], "level", 1000.0) == 7_443_000.0
    assert derived._transform([4.1], "level", 1.0) == 4.1


def test_flag_off_produces_nothing(monkeypatch):
    monkeypatch.delenv("EYAY_MACRO_MATRIX_ENABLED", raising=False)
    assert derived.releases(datetime(2026, 10, 30, tzinfo=UTC)) == []


def test_flag_on_derives_calendar_units(monkeypatch):
    from packages.data.providers.price import fred

    monkeypatch.setenv("EYAY_MACRO_MATRIX_ENABLED", "true")
    quarters = [SimpleNamespace(ts=datetime(2025 + (m // 12), m % 12 + 1, 1, tzinfo=UTC), close=2.0) for m in range(6, 21, 3)]
    series = {"PAYEMS": _months([159_000.0 + 100 * i for i in range(13)] + [159_254.0 + 1200.0]),
              "UNRATE": _months([4.1] * 14), "A191RL1Q225SBEA": quarters}
    monkeypatch.setattr(fred, "get_series", lambda sid, start=None: series.get(sid, _months([100.0 + i for i in range(14)])))
    rows = {r.title: r for r in derived.releases(datetime(2026, 10, 30, tzinfo=UTC))}
    nfp = rows["US Nonfarm Payrolls"]
    assert nfp.unit == "scaled_count" and nfp.actual == pytest.approx(254_000.0)
    assert nfp.ts == datetime(2026, 9, 30, 12, tzinfo=UTC) and nfp.verified is True
    assert rows["US Unemployment Rate"].actual == 4.1
    assert rows["US CPI (MoM)"].unit == "percent"
    assert rows["US GDP (QoQ)"].ts == datetime(2026, 9, 30, 12, tzinfo=UTC)  # çeyrek sonu


def test_join_rules_only_for_derived_rows():
    official = _derived_cpi()
    assert derived.compatible(official, _calendar()) is True
    assert derived.compatible(official, _calendar(title="CPI (YoY)")) is False          # ölçü farklı
    assert derived.compatible(official, _calendar(day=13, month=11, actual=None)) is False  # sonraki ayın beklentisi
    assert derived.compatible(official, _calendar(actual=0.5)) is False                 # yayımlanan gerçekleşenle uyuşmuyor
    assert derived.compatible(_calendar(), _calendar()) is None                        # türetilmemiş satır: eski kural


def _snapshot(**kwargs):
    rotation = SimpleNamespace(status="OK", per_symbol={"DXY": 70.0, "XAUUSD": 58.0}, evidence=["fixture"])
    values = {"generated_at": datetime.now(UTC), "rotation": rotation, "quality": SimpleNamespace(status="OK", score=90.0),
              "headlines": [], "catalysts": [], "catalyst_impacts": [], "macro_releases": []}
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_calendar_expectation_attached_without_snapshot_limit(monkeypatch):
    from packages.data.providers.calendar import web as web_calendar
    from packages.data.providers.price import fred

    monkeypatch.setenv("EYAY_MACRO_MATRIX_ENABLED", "true")
    monkeypatch.setattr(fred, "get_series", lambda sid, start=None: _months([100.0 + 0.3 * i for i in range(14)]))
    monkeypatch.setattr(web_calendar, "list_catalysts", lambda now=None, horizon_days=2: [
        _calendar(actual=None, expected=0.2), _calendar(title="Core CPI (MoM)", actual=None, expected=0.3)])
    rows = {r.title: r for r in derived.releases(datetime(2026, 10, 15, tzinfo=UTC))}
    assert rows["US CPI (MoM)"].expected == 0.2
    assert rows["US CPI (MoM)"].ts == datetime(2026, 10, 14, 12, 30, tzinfo=UTC)  # azalma açıklama anından
    assert rows["US CPI (MoM)"].id.endswith(":2026-09-30")                       # dönem kimlikte
    assert rows["US Core CPI (MoM)"].expected == 0.3          # çekirdek satır çekirdek beklentiyi alır
    assert rows["US CPI (YoY)"].expected is None              # ölçüsü uyan beklenti yok
    assert any(e.startswith("expectation_join=") for e in rows["US CPI (MoM)"].evidence)


def test_surprise_is_finally_computed_end_to_end():
    snap = _snapshot(catalysts=[_calendar(), _calendar(title="CPI (YoY)", actual=3.1, expected=3.0)],
                     macro_releases=[_derived_cpi()])
    world = build(snap)
    official = [s for s in world.macro_surprises if s.verified]
    assert len(official) == 1  # takvim MoM satırı ayrıca sayılmadı
    assert not any(s.event_id == "cal-CPI (MoM)-10-14" for s in world.macro_surprises)
    surprise = official[0]
    assert surprise.raw_surprise == pytest.approx(0.1) and surprise.normalization_method == "historical_volatility"
    rows = {r["asset"]: r for r in build_macro_evidence(snap) if r["verified"]}
    assert rows["DXY"]["direction"] == "bullish" and rows["XAUUSD"]["direction"] == "bearish"
    assert rows["XAUUSD"]["expected"] == 0.2 and rows["XAUUSD"]["actual"] == 0.3
