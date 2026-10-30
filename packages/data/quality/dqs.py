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

from packages.data.registry import assets as asset_registry
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


_SOURCE_FRESHNESS_WINDOWS_SEC: dict[str, int] = {
    # FRED serileri günlük/aylık güncellenir. 5 dakikalık bir fiyat penceresi
    # uygulamak, geçerli makro veriyi yanlışlıkla bayat sayıyordu.
    "fred": 172_800,
    # Günlük Yahoo kapanışı, piyasa kapalıyken bir sonraki seansa kadar geçerli
    # bir gözlemdir. Teknik bar tazeliği ayrıca kendi kapısından geçer.
    "yfinance": 21_600,
    # CoinGecko modülü 15 dk TTL ile çalışır; küçük bir ağ/worker gecikmesi payı.
    "coingecko": 1_800,
    "twelvedata": 3_600,
    "alphavantage": 3_600,
    "finnhub": 1_800,
}


def _freshness_window(source: str, default: int) -> int:
    """Quote kaynağının doğal güncelleme aralığını döndür.

    Bu yalnızca DQS ölçümüdür; karar motorunun teknik-bar ve işlem-session
    kapıları aynı kalır. Bilinmeyen kaynaklar için sıkı varsayılan korunur.
    """
    key = str(source or "").strip().lower()
    return _SOURCE_FRESHNESS_WINDOWS_SEC.get(key, default)


def _freshness(quotes: list[PriceQuote], max_age_sec: int = 300) -> float:
    if not quotes:
        return 0.0
    now = datetime.now(UTC)
    scores: list[float] = []
    for q in quotes:
        age = max(0.0, (now - q.ts).total_seconds())
        window = _freshness_window(q.source, max_age_sec)
        scores.append(max(0.0, min(100.0, 100.0 * (1.0 - min(age / window, 1.0)))))
    return sum(scores) / len(scores)


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
        "technical_session_coverage": None,
        "news_diversity": None,
        "rotation_coverage": None,
        "artifact_freshness": None,
    }
    # Teknik bar kalitesi: (sembol × TF) hücrelerinin yüzde kaçı tam-bar (≥200)
    # ve indikatör tabanı hazır. Piyasa kapalıyken intraday son barın stale
    # olması beklenen bir durumdur; bunu ayrı `technical_session_coverage`
    # ekseninde gösteririz, tarihçe yeterliyse bar kalitesini düşürmeyiz.
    try:
        # Discovery/custom assets are intentionally not in this denominator:
        # this axis measures the decision universe, not every exploratory
        # series that happens to be present in the snapshot.
        trade_symbols = set(asset_registry.configured_trade_symbols())
        cells = [
            (symbol, t)
            for symbol, by_tf in (technicals_by_tf or {}).items()
            if symbol in trade_symbols
            for t in by_tf.values()
        ]
        if cells:
            current = now or datetime.now(UTC)

            def _closed_session(symbol: str) -> bool:
                try:
                    from packages.market_sessions import asset_context

                    ctx = asset_context(symbol, current)
                    return bool(
                        ctx.relevant_markets
                        and not ctx.any_relevant_market_open
                        and ctx.session_risk != "unknown"
                    )
                except (OSError, TypeError, ValueError):
                    return False

            full = sum(
                1 for symbol, t in cells
                if int(getattr(t, "bars_used", 0) or 0) >= 200
                and (
                    getattr(t, "status", "") == "OK"
                    or _closed_session(symbol)
                )
            )
            out["technical_bars"] = round(100.0 * full / len(cells), 1)
            # A closed exchange cannot publish a new intraday candle. The
            # same closed-session allowance is reflected in this separate
            # coverage axis; entry freshness/status remains unchanged in the
            # technical snapshot and still blocks stale data.
            out["technical_session_coverage"] = round(100.0 * full / len(cells), 1)
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


def compute(
    quotes: list[PriceQuote],
    expected: list[str],
    *,
    optional_symbols: set[str] | frozenset[str] | None = None,
) -> QualityReport:
    """Compute quality for the decision-critical price universe.

    Runtime-discovered/custom assets remain visible in the snapshot, but a
    missing quote for one optional candidate must not close the entire core
    universe through the global DQS cap.  The omission is reported explicitly
    in ``notes``.  Callers that omit ``optional_symbols`` retain the original
    all-symbol behaviour.
    """
    optional = set(optional_symbols or ())
    required = [symbol for symbol in expected if symbol not in optional]
    decision_quotes = [quote for quote in quotes if quote.symbol not in optional]

    # Preserve the isolated mock-only simulation contract.
    priced = [q for q in decision_quotes if q.price is not None]
    mock_only = bool(priced) and all(q.status == "MOCK" for q in priced)

    # A live quote is usable only with an explicitly verified, OK price.
    trusted = [
        q for q in decision_quotes
        if q.price is not None and q.verified and q.status == "OK"
    ]

    fr = _freshness(decision_quotes)
    co = _completeness(
        decision_quotes if mock_only else trusted,
        required,
    )
    dr = _drift(decision_quotes)
    rc = _reconciliation(decision_quotes)
    du, fb = _decision_usage(decision_quotes)
    score = round(
        0.20 * fr + 0.30 * co + 0.15 * dr + 0.10 * rc + 0.25 * du,
        1,
    )
    # Live data must not get an OK score from unverified/missing
    # expected assets. The numeric cap also reaches RiskGate, which
    # evaluates dqs_score rather than the textual status.
    # Mock-only test fixtures preserve their previous behavior.
    if not mock_only:
        if not trusted:
            score = 0.0
        elif required:
            expected_symbols = set(required)
            trusted_symbols = {q.symbol for q in trusted}
            coverage = 100.0 * len(
                trusted_symbols & expected_symbols
            ) / len(expected_symbols)
            if coverage < 100.0:
                score = round(min(score, coverage, 69.9), 1)
    status = _status(score, co)
    notes: list[str] = []
    missing = [s for s in required if not any(q.symbol == s and q.price is not None for q in quotes)]
    if missing:
        notes.append(f"veri yok: {', '.join(missing)}")
    optional_missing = [
        s for s in expected
        if s in optional and not any(q.symbol == s and q.price is not None for q in quotes)
    ]
    if optional_missing:
        notes.append(f"opsiyonel varlık verisi yok: {', '.join(optional_missing)}")
    unverified = [q.symbol for q in decision_quotes if not q.verified and q.price is not None]
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
