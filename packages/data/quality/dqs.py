"""Data Quality Score — 5 concern, tek dosya.

Eski projedeki 150 snapshot_replay_source_quality_* dosyası yerine
bütün kalite kontrolleri burada toplandı:

  1) freshness    — kaynak ne kadar bayat
  2) completeness — eksik veri yok mu
  3) drift        — değerler beklenen bant içinde mi
  4) reconciliation — kaynaklar arası tutarlılık
  5) decision_usage_consistency — verified_required kaynak fallback'a düştü mü
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.data.types import PriceQuote


@dataclass
class QualityReport:
    score: float                  # 0–100
    freshness: float              # 0–100
    completeness: float           # 0–100
    drift: float                  # 0–100
    reconciliation: float         # 0–100
    decision_usage: float         # 0–100
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
    have = {q.symbol for q in quotes}
    return 100.0 * len(have & set(expected)) / len(expected)


def _drift(quotes: list[PriceQuote]) -> float:
    if not quotes:
        return 50.0
    bad = sum(1 for q in quotes if q.price <= 0 or q.price > 1_000_000)
    return max(0.0, 100.0 - 25.0 * bad)


def _reconciliation(quotes: list[PriceQuote]) -> float:
    # Mock için trivial; v2.1'de cross-source aynı sembol karşılaştırılır.
    return 100.0 if quotes else 50.0


def _decision_usage(quotes: list[PriceQuote]) -> tuple[float, bool]:
    fallback = any(q.fallback for q in quotes)
    return (60.0 if fallback else 100.0, fallback)


def compute(quotes: list[PriceQuote], expected: list[str]) -> QualityReport:
    fr = _freshness(quotes)
    co = _completeness(quotes, expected)
    dr = _drift(quotes)
    rc = _reconciliation(quotes)
    du, fb = _decision_usage(quotes)
    # Ağırlıklı toplam — completeness ve decision_usage daha kritik
    score = round(
        0.20 * fr + 0.30 * co + 0.15 * dr + 0.10 * rc + 0.25 * du,
        1,
    )
    notes: list[str] = []
    if fb:
        notes.append("fallback kaynak kullanıldı")
    if co < 100:
        notes.append(f"completeness düştü: {co:.0f}%")
    if fr < 60:
        notes.append("kaynaklar bayatlıyor")
    return QualityReport(
        score=score,
        freshness=round(fr, 1),
        completeness=round(co, 1),
        drift=round(dr, 1),
        reconciliation=round(rc, 1),
        decision_usage=round(du, 1),
        fallback_used=fb,
        notes=notes,
    )
