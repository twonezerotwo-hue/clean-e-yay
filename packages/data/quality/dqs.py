"""Data Quality Score — 5 concern, tek dosya.

Politika ([docs/DATA_POLICY.md]):
- `price is None` veya `verified=False` quote'lar gerçek kullanılabilir
  veri sayılmaz; completeness ve decision_usage düşer.
- Tüm semboller None ise score=0, status=BLOCKED.
- Status alanı `OK / DEGRADED / BLOCKED` enum'u; risk gate ve dashboard
  bu damgayı okur.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from packages.data.types import PriceQuote

QualityStatus = Literal["OK", "DEGRADED", "BLOCKED"]


@dataclass
class QualityReport:
    score: float
    freshness: float
    completeness: float
    drift: float
    reconciliation: float
    decision_usage: float
    status: QualityStatus = "OK"
    fallback_used: bool = False
    notes: list[str] = field(default_factory=list)


def _freshness(quotes: list[PriceQuote], max_age_sec: int = 300) -> float:
    if not quotes:
        return 0.0
    now = datetime.now(UTC)
    ages = [(now - q.ts).total_seconds() for q in quotes]
    avg = sum(ages) / len(ages)
    return max(0.0, min(100.0, 100.0 * (1.0 - min(avg / max_age_sec, 1.0))))


def _completeness(quotes: list[PriceQuote], expected: list[str]) -> float:
    if not expected:
        return 100.0
    have = {q.symbol for q in quotes if q.price is not None}
    return 100.0 * len(have & set(expected)) / len(expected)


def _drift(quotes: list[PriceQuote]) -> float:
    valid = [q for q in quotes if q.price is not None]
    if not valid:
        return 0.0
    bad = sum(1 for q in valid if q.price <= 0 or q.price > 1_000_000)
    return max(0.0, 100.0 - 25.0 * bad)


def _reconciliation(quotes: list[PriceQuote]) -> float:
    return 100.0 if any(q.price is not None for q in quotes) else 0.0


def _decision_usage(quotes: list[PriceQuote]) -> tuple[float, bool]:
    if not quotes:
        return (0.0, True)
    verified_with_value = sum(
        1 for q in quotes if q.verified and q.price is not None
    )
    fb = verified_with_value < len(quotes)
    return (100.0 * verified_with_value / len(quotes), fb)


def _status(score: float, completeness: float) -> QualityStatus:
    if score < 40 or completeness <= 0:
        return "BLOCKED"
    if score < 70:
        return "DEGRADED"
    return "OK"


def compute(quotes: list[PriceQuote], expected: list[str]) -> QualityReport:
    fr = _freshness(quotes)
    co = _completeness(quotes, expected)
    dr = _drift(quotes)
    rc = _reconciliation(quotes)
    du, fb = _decision_usage(quotes)
    score = round(
        0.20 * fr + 0.30 * co + 0.15 * dr + 0.10 * rc + 0.25 * du,
        1,
    )
    status = _status(score, co)
    notes: list[str] = []
    missing = [s for s in expected if not any(q.symbol == s and q.price is not None for q in quotes)]
    if missing:
        notes.append(f"veri yok: {', '.join(missing)}")
    unverified = [q.symbol for q in quotes if not q.verified and q.price is not None]
    if unverified:
        notes.append("doğrulanmamış kaynak (mock/test)")
    if status == "BLOCKED":
        notes.append("DQS BLOCKED — yeni karar üretilmez")
    return QualityReport(
        score=score,
        freshness=round(fr, 1),
        completeness=round(co, 1),
        drift=round(dr, 1),
        reconciliation=round(rc, 1),
        decision_usage=round(du, 1),
        status=status,
        fallback_used=fb,
        notes=notes,
    )
