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
    # 2026-07-13 dış denetim P1 — genişletilmiş alt-metrikler (GÖZLEM-YALNIZ:
    # score/status hesabına GİRMEZ; DQS'in yalnız fiyat-quote ölçtüğü kör nokta
    # görünür olsun diye). None = o eksen bu snapshot'ta ölçülemedi.
    extended: dict | None = None


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


def extended_metrics(
    *,
    technicals_by_tf: dict | None = None,
    headlines: list | None = None,
    rotation=None,
    now: datetime | None = None,
) -> dict:
    """Genişletilmiş DQS alt-metrikleri (2026-07-13 dış denetim P1, GÖZLEM-YALNIZ).

    Kör nokta: DQS yalnız PriceQuote ölçüyordu — teknik barlar, haber çeşitliliği,
    rotasyon kapsaması veya öğrenme artifact'ı bozukken genel DQS yüksek
    kalabiliyordu. Bu metrikler score/status'a GİRMEZ (karar davranışı bayt-aynı);
    her snapshot'ta `dqs_extended:` warning satırı + rapor alanı olarak birikir.
    Kapsam eksenleri: 0-100 (yüksek = sağlıklı); None = ölçülemedi."""
    out: dict[str, float | None] = {
        "technical_bars": None,
        "news_diversity": None,
        "rotation_coverage": None,
        "artifact_freshness": None,
    }
    # Teknik bar kalitesi: (sembol × TF) hücrelerinin yüzde kaçı tam-bar (≥200)
    # ve OK statüde. Kısıtlı bar = zayıf indikatör tabanı (RSI/trend güvensiz).
    try:
        cells = [t for by_tf in (technicals_by_tf or {}).values() for t in by_tf.values()]
        if cells:
            full = sum(
                1 for t in cells
                if getattr(t, "status", "") == "OK"
                and int(getattr(t, "bars_used", 0) or 0) >= 200
            )
            out["technical_bars"] = round(100.0 * full / len(cells), 1)
    except (TypeError, ValueError, AttributeError):
        pass
    # Haber kaynak çeşitliliği: verified başlıklardaki FARKLI kaynak sayısı
    # (≥3 kaynak = 100). Tek kaynağa çökmüş haber beslemesi görünür olur.
    try:
        if headlines is not None:
            srcs = {getattr(h, "source", None) for h in headlines if getattr(h, "verified", False)}
            srcs.discard(None)
            out["news_diversity"] = round(min(100.0, 100.0 * len(srcs) / 3.0), 1)
    except TypeError:
        pass
    # Rotasyon kapsaması: evren OK + sembol-başı skor var mı (quantum v2 tabanı).
    try:
        if rotation is not None:
            if getattr(rotation, "status", "") == "OK":
                out["rotation_coverage"] = 100.0 if (getattr(rotation, "per_symbol", None) or {}) else 60.0
            else:
                out["rotation_coverage"] = 0.0
    except TypeError:
        pass
    # Öğrenme artifact tazeliği: tf_scoring artifact'ının yaşı / 3h tavanı
    # (consensus zaten 3h+ bayatta zemine düşer — burada worker sağlığı görünür).
    try:
        import json as _json

        from packages.learning import tf_scoring_shadow

        p = tf_scoring_shadow.artifact_path()
        if p.exists():
            gen = datetime.fromisoformat(
                str(_json.loads(p.read_text(encoding="utf-8")).get("generated_at"))
            )
            age = ((now or datetime.now(UTC)) - gen).total_seconds()
            out["artifact_freshness"] = round(
                max(0.0, min(100.0, 100.0 * (1.0 - age / 10800.0))), 1
            )
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return out


_GATE_AXES = ("technical_bars", "news_diversity", "rotation_coverage", "artifact_freshness")


def apply_extended_gate(report: QualityReport, cfg: dict | None) -> QualityReport:
    """M14 observe→eşik (FAZ-2, 2026-07-16): genişletilmiş eksen eşiğin altında
    ise snapshot status OK→DEGRADED (provenance "karar live sayılmaz" etiketi).

    Sınırlar (bilinçli):
    - SKORA DOKUNMAZ — skor<55 risk-engine KILL_SWITCH zinciri bu kapıdan
      kazayla tetiklenemez; kapının tek yetkisi dürüstlük etiketi.
    - Yalnız KÖTÜLEŞTİRİR: OK→DEGRADED. BLOCKED zaten en kötü (dokunulmaz),
      DEGRADED'i yükseltmez. Not satırı her ihlalde eklenir (görünürlük).
    - Eşiği 0 olan eksen kapıdan MUAF (yalnız-gözlem sürer); değeri None olan
      eksen o snapshot'ta ölçülemedi demektir, ihlal SAYILMAZ (uydurma yok).
    - `enabled: false` → rapor bayt-aynı (gölge-önce kuralı)."""
    if not cfg or not cfg.get("enabled", False) or not report.extended:
        return report
    breaches: list[str] = []
    for axis in _GATE_AXES:
        try:
            floor_ = float(cfg.get(f"{axis}_min", 0.0) or 0.0)
        except (TypeError, ValueError):
            floor_ = 0.0
        val = report.extended.get(axis)
        if floor_ > 0 and val is not None and float(val) < floor_:
            breaches.append(f"{axis}={val}<{floor_:g}")
    if breaches:
        report.notes.append("dqs_extended_gate: " + ", ".join(breaches))
        if report.status == "OK":
            report.status = "DEGRADED"
    return report


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
