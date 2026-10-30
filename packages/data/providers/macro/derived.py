"""Resmî FRED serilerinden takvimle aynı birim ve ölçüde gerçekleşen değer.

Hedef mimari 2b (kh_macro). Takvim beklentisi "aylık % değişim", "yıllık %
değişim" ya da "bin kişi değişim" olarak gelir; resmî seri ise endeks ya da
seviyedir, bu yüzden sürpriz hiç hesaplanamıyordu. Bu modül gerçekleşeni aynı
birimde türetir. Satırlar ``source="fred_derived"`` taşır ve yalnız onlara
`compatible()` uygulanır: ölçü (MoM/YoY/QoQ) aynı olmalı, takvim satırı resmî
dönemin bilinen açıklama gecikmesi içinde olmalı, takvimde gerçekleşen varsa
resmîyle uyuşmalı. Yalnız EYAY_MACRO_MATRIX_ENABLED açıkken üretilir.
"""
from __future__ import annotations

import calendar
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from packages.data.types import Catalyst

log = logging.getLogger(__name__)

SOURCE = "fred_derived"


@dataclass(frozen=True)
class Spec:
    key: str
    series: str
    title: str
    how: str          # mom | yoy | diff | level
    unit: str         # takvim birimi: percent | scaled_count
    scale: float      # seviye → takvim ölçeği (bin kişi → kişi)
    quarterly: bool
    lag_days: tuple[int, int]  # dönem sonu → açıklama günü
    sigma: float      # ilk normalleştirme ölçeği; olay çalışması ölçer
    match: tuple[str, ...]     # takvim başlığında aranan ifadeler
    exclude: tuple[str, ...] = ()


SPECS: tuple[Spec, ...] = (
    Spec("CPI_MOM", "CPIAUCSL", "US CPI (MoM)", "mom", "percent", 1.0, False, (0, 20), 0.2, ("cpi", "consumer price"), ("core",)),
    Spec("CPI_YOY", "CPIAUCNS", "US CPI (YoY)", "yoy", "percent", 1.0, False, (0, 20), 0.2, ("cpi", "consumer price"), ("core",)),
    Spec("CORE_CPI_MOM", "CPILFESL", "US Core CPI (MoM)", "mom", "percent", 1.0, False, (0, 20), 0.2, ("core cpi", "core consumer price")),
    Spec("CORE_CPI_YOY", "CPILFENS", "US Core CPI (YoY)", "yoy", "percent", 1.0, False, (0, 20), 0.2, ("core cpi", "core consumer price")),
    Spec("PPI_MOM", "PPIFIS", "US PPI (MoM)", "mom", "percent", 1.0, False, (0, 20), 0.3, ("ppi", "producer price"), ("core",)),
    Spec("PCE_MOM", "PCEPI", "US PCE Price Index (MoM)", "mom", "percent", 1.0, False, (15, 40), 0.15, ("pce price", "personal consumption expenditures price"), ("core",)),
    Spec("PCE_YOY", "PCEPI", "US PCE Price Index (YoY)", "yoy", "percent", 1.0, False, (15, 40), 0.2, ("pce price", "personal consumption expenditures price"), ("core",)),
    Spec("CORE_PCE_MOM", "PCEPILFE", "US Core PCE Price Index (MoM)", "mom", "percent", 1.0, False, (15, 40), 0.15, ("core pce",)),
    Spec("CORE_PCE_YOY", "PCEPILFE", "US Core PCE Price Index (YoY)", "yoy", "percent", 1.0, False, (15, 40), 0.2, ("core pce",)),
    Spec("NFP", "PAYEMS", "US Nonfarm Payrolls", "diff", "scaled_count", 1000.0, False, (0, 12), 100_000.0, ("nonfarm payrolls", "non-farm payrolls"), ("private",)),
    Spec("UNEMPLOYMENT", "UNRATE", "US Unemployment Rate", "level", "percent", 1.0, False, (0, 12), 0.2, ("unemployment rate",)),
    Spec("JOLTS", "JTSJOL", "US JOLTS Job Openings", "level", "scaled_count", 1000.0, False, (25, 45), 500_000.0, ("jolts", "job openings")),
    Spec("GDP_QOQ", "A191RL1Q225SBEA", "US GDP (QoQ)", "level", "percent", 1.0, True, (20, 35), 1.0, ("gdp",), ("price", "deflator", "sales")),
)
_BY_TITLE = {spec.title: spec for spec in SPECS}


def enabled() -> bool:
    """packages.macro.matrix.enabled ile aynı bayrak (döngüsel içe aktarımı önlemek için burada okunur)."""
    return os.environ.get("EYAY_MACRO_MATRIX_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def measure_of(title: str | None) -> str | None:
    text = str(title or "").casefold()
    if re.search(r"\bm/m\b|\(mom\)|\bmom\b|month over month", text):
        return "mom"
    if re.search(r"\by/y\b|\(yoy\)|\byoy\b|year over year", text):
        return "yoy"
    if re.search(r"\bq/q\b|\(qoq\)|\bqoq\b|annuali[sz]ed", text):
        return "qoq"
    return None


_US = {"us", "usa", "u.s.", "usd", "united states"}


def _matches(spec: Spec, row: Any) -> bool:
    title = str(getattr(row, "title", "") or "").casefold()
    region = str(getattr(row, "region", "") or "").casefold().strip()
    return (region in _US and any(word in title for word in spec.match)
            and not any(word in title for word in spec.exclude))


def _period_end(ts: datetime, quarterly: bool) -> datetime:
    year, month = ts.year, ts.month + (2 if quarterly else 0)
    last = calendar.monthrange(year, month)[1]
    return datetime(year, month, last, 12, tzinfo=UTC)


def _transform(values: list[float], how: str, scale: float) -> float | None:
    """`values` eskiden yeniye; son eleman hesaplanan dönem."""
    try:
        if how == "mom":
            return round((values[-1] / values[-2] - 1.0) * 100.0, 1)
        if how == "yoy":
            return round((values[-1] / values[-13] - 1.0) * 100.0, 1)
        if how == "diff":
            return round((values[-1] - values[-2]) * scale, 0)
        if how == "level":
            return round(values[-1] * scale, 1 if scale == 1.0 else 0)
    except (IndexError, ZeroDivisionError):
        return None
    return None


def releases(now: datetime | None = None) -> list[Catalyst]:
    if not enabled():
        return []
    from packages.data.providers.price import fred

    now = now or datetime.now(UTC)
    start = (now - timedelta(days=500)).date().isoformat()
    calendar_rows = _calendar_rows(now)
    out: list[Catalyst] = []
    for spec in SPECS:
        try:
            bars = fred.get_series(spec.series, start=start)
        except Exception as exc:  # tek seri hatası diğerlerini durdurmaz
            log.warning("fred_derived %s: %s", spec.series, type(exc).__name__)
            continue
        values = [float(bar.close) for bar in bars]
        if len(values) < 3:
            continue
        actual = _transform(values, spec.how, spec.scale)
        previous = _transform(values[:-1], spec.how, spec.scale)
        if actual is None:
            continue
        ts = _period_end(bars[-1].ts, spec.quarterly)
        row = Catalyst(
            id=f"FRED_DERIVED_{spec.key}:{ts.date().isoformat()}", ts=ts, title=spec.title,
            importance="high", region="US", category=f"FRED_DERIVED_{spec.key}_OFFICIAL",
            market_impact="official FRED series; actual derived in calendar units",
            days_until=(ts.date() - now.date()).days, hours_until=round((ts - now).total_seconds() / 3600, 1),
            source=SOURCE, verified=True, actual=actual, previous=previous, unit=spec.unit,
            historical_surprise_volatility=spec.sigma,
            evidence=["Federal Reserve Bank of St. Louis FRED", f"series={spec.series}", f"derived={spec.how}"],
        )
        out.append(_attach_expectation(row, spec, calendar_rows))
    return out


def _calendar_rows(now: datetime) -> list[Any]:
    """Web takviminin önbellekteki satırları (açıklama günü ve sonrası); 8 satır sınırına takılmaz."""
    try:
        from packages.data.providers.calendar import web as web_calendar

        return [r for r in web_calendar.list_catalysts(now=now, horizon_days=2) if getattr(r, "expected", None) is not None]
    except Exception:
        return []


def _attach_expectation(row: Catalyst, spec: Spec, calendar_rows: list[Any]) -> Catalyst:
    candidates = [c for c in calendar_rows if _matches(spec, c) and compatible(row, c)]
    if not candidates:
        return row
    best = min(candidates, key=lambda c: abs((c.ts - row.ts).total_seconds()))
    return row.model_copy(update={
        "expected": best.expected,
        "ts": best.ts,  # sürpriz açıklama anından itibaren azalır; dönem sonu kimlikte
        "evidence": [*row.evidence, f"expectation_join={best.id}"],
    })


def period_end(row: Any) -> datetime | None:
    """Türetilmiş satırın dönem sonu (kimlikten); yoksa satırın zamanı."""
    try:
        return datetime.fromisoformat(str(getattr(row, "id", "")).rsplit(":", 1)[1]).replace(hour=12, tzinfo=UTC)
    except (IndexError, ValueError):
        ts = getattr(row, "ts", None)
        return ts if isinstance(ts, datetime) else None


def compatible(actual_row: Any, expected_row: Any) -> bool | None:
    """Türetilmiş satır için eşleşme kuralı; türetilmiş değilse None (eski kural geçerli)."""
    if getattr(actual_row, "source", None) != SOURCE:
        return None
    spec = _BY_TITLE.get(str(getattr(actual_row, "title", "")))
    if spec is None or measure_of(spec.title) != measure_of(getattr(expected_row, "title", None)):
        return False
    if not _matches(spec, expected_row):
        return False
    a_ts, e_ts = period_end(actual_row), getattr(expected_row, "ts", None)
    if not isinstance(a_ts, datetime) or not isinstance(e_ts, datetime):
        return False
    lag = (e_ts.date() - a_ts.date()).days
    if not spec.lag_days[0] <= lag <= spec.lag_days[1]:
        return False
    published = getattr(expected_row, "actual", None)
    official = getattr(actual_row, "actual", None)
    if published is not None and official is not None:
        tolerance = 0.051 if spec.unit == "percent" else max(abs(float(published)) * 0.015, 3000.0)
        if abs(float(published) - float(official)) > tolerance:
            return False
    return True
