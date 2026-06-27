"""Elliott Wave Scenario Engine — top-level `analyze()` (EVIDENCE only).

Gerçek OHLCV barlarından fraktal pivot dizisi çıkarır, impulse (1-2-3-4-5)
ve zigzag (A-B-C) hard-rule kontrolü yapar, NO_VALID_COUNT'a düşmeden tek
bir "doğru" sayım iddia etmez (spec §10.1/§10.6). Kullanıcıdan sayım almaz;
otomatik üretir.

Bu motor:
- HİÇBİR trade açmaz, HİÇBİR skor/consensus'a karışmaz.
- Hiçbir setup'ın ön koşulu DEĞİLDİR — NO_VALID_COUNT meşru bir sonuçtur;
  çağıran taraf (decision/agent_pipeline, ileride) diğer kanıtlarla devam
  edebilir. Bu modül kendi kararını dayatmaz.
- `packages/data/providers/technical/fibonacci.py` ile aynı deseni izler:
  pure fonksiyon, validity/diagnostics, uydurma seviye yok.

Henüz hiçbir canlı karar zincirine (decide_for_symbol / decide_matrix /
agent_pipeline) bağlı DEĞİLDİR — yalnızca read-only API yüzeyinden erişilir
(bkz. apps/api/routers/technical.py::get_elliott_scenario). Bu, mevcut
sistemin "shadow / additive read surface" desenidir (packages/decision/
shadow.py, agent_pipeline.py docstring'lerindeki ilke) — canlı kararı
etkilemeden gözlemlenebilir olması için bilinçli bir tasarım.
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds
from packages.data.types import ElliottAnalysis, ElliottWavePoint
from packages.elliott import wave_rules
from packages.elliott.pivots import Pivot, last_n_alternating

# Hard-rule'lardan hangileri ihlal edilirse sayım GEÇERSİZ sayılır (spec
# §10.4 — yalnızca "Wave2 Wave1'i geçmemeli" ve "Wave4 Wave1 alanına
# girmemeli" disqualifying'dir; "not_shortest"/"extends" sadece confidence'ı
# düşürür, sayımı tek başına geçersiz kılmaz).
_IMPULSE_HARD_RULES = {"wave2_no_breach_wave0", "wave4_no_overlap_wave1"}
_ABC_HARD_RULES = {"a_extends_from_p0", "c_extends_beyond_a"}

# Defaults — `config/thresholds_v1.0.yaml::elliott` bunları override eder.
_DEFAULT_PIVOT_LEFT = 3
_DEFAULT_PIVOT_RIGHT = 3
_DEFAULT_FIB_PROJECTION = (0.618, 1.0, 1.618)


def _cfg() -> dict:
    try:
        return load_thresholds().get("elliott") or {}
    except (OSError, KeyError, ValueError):
        return {}


def _default_pivot_window() -> tuple[int, int]:
    c = _cfg()
    return (
        int(c.get("pivot_left", _DEFAULT_PIVOT_LEFT)),
        int(c.get("pivot_right", _DEFAULT_PIVOT_RIGHT)),
    )


def _fib_projection() -> tuple[float, ...]:
    proj = _cfg().get("fib_projection")
    if isinstance(proj, list) and len(proj) >= 2:
        return tuple(float(x) for x in proj)
    return _DEFAULT_FIB_PROJECTION


def _wave_points(points: list[Pivot], labels: list[str]) -> list[ElliottWavePoint]:
    return [
        ElliottWavePoint(label=lbl, bar_index=p.bar_index, price=p.price, ts=p.ts)
        for lbl, p in zip(labels, points, strict=True)
    ]


def _start_diag(points: list[Pivot], labels: list[str]) -> str:
    """Sayımın nereden başladığını açıkça yazan ilk satır (spec: 'P0' tek başına
    yetersiz — bar/fiyat/zaman göstermeli)."""
    p0 = points[0]
    when = f", {p0.ts}" if p0.ts else ""
    return f"Sayım {labels[0]}'dan başladı: bar #{p0.bar_index}, fiyat {p0.price:.4f}{when}"


_IMPULSE_RULE_EXPLAIN = {
    "wave2_no_breach_wave0": (
        lambda p, up: (
            f"Wave 2 kuralı ihlal: P2 ({p[2]:.4f}) dalga 1 başlangıcı P0'ı "
            f"({p[0]:.4f}) {'aşağı geçti' if up else 'yukarı geçti'} — "
            f"{'P2 > P0 olmalıydı' if up else 'P2 < P0 olmalıydı'}"
        )
    ),
    "wave4_no_overlap_wave1": (
        lambda p, up: (
            f"Wave 4 overlap kuralı ihlal: P4 ({p[4]:.4f}) dalga 1 bölgesine "
            f"(P1: {p[1]:.4f}) girdi — {'P4 > P1 olmalıydı' if up else 'P4 < P1 olmalıydı'}"
        )
    ),
    "wave3_not_shortest": (
        lambda p, up: (
            f"Wave 3 en kısa dalga: |P3-P2|={abs(p[3]-p[2]):.4f}, "
            f"|P1-P0|={abs(p[1]-p[0]):.4f}, |P5-P4|={abs(p[5]-p[4]):.4f} — "
            "dalga 3 üç dalganın en kısası olamaz"
        )
    ),
    "wave3_extends_wave1": (
        lambda p, up: (
            f"Wave 3 dalga 1'i uzatmadı: P3 ({p[3]:.4f}) P1'i "
            f"({p[1]:.4f}) {'yeni high ile' if up else 'yeni low ile'} geçmedi"
        )
    ),
}

_ABC_RULE_EXPLAIN = {
    "a_extends_from_p0": (
        lambda p, down: (
            f"A dalgası P0'dan yeterince uzaklaşmadı: A ({p[1]:.4f}) "
            f"P0'a ({p[0]:.4f}) göre {'aşağı' if down else 'yukarı'} hareket etmedi"
        )
    ),
    "b_within_p0_retracement": (
        lambda p, down: (
            f"B dalgası P0'ı geçti: B ({p[2]:.4f}) başlangıç noktası P0'ı "
            f"({p[0]:.4f}) aştı — basit zigzag değil"
        )
    ),
    "c_extends_beyond_a": (
        lambda p, down: (
            f"C dalgası A'nın ötesine uzanmadı: C ({p[3]:.4f}) A'yı ({p[1]:.4f}) "
            f"{'aşağı' if down else 'yukarı'} geçmedi"
        )
    ),
}


def _target_zone(anchor: float, length: float, *, up: bool) -> tuple[float, float]:
    proj = _fib_projection()
    lo_ratio, hi_ratio = proj[0], proj[-1]
    if up:
        return (round(anchor + lo_ratio * length, 6), round(anchor + hi_ratio * length, 6))
    return (round(anchor - hi_ratio * length, 6), round(anchor - lo_ratio * length, 6))


def _try_impulse(points: list[Pivot]) -> tuple[bool, ElliottAnalysis]:
    """Her zaman bir ElliottAnalysis döner — geçersizse de wave_points +
    açıklayıcı diagnostics taşır (sayım nereden başladı, hangi kural neye
    göre ihlal edildi). `analyze()` ilk eleman False ise NO_VALID_COUNT'a
    düşer ama bu analysis'in diagnostics'ini kullanıcıya gösterir."""
    results = wave_rules.check_impulse_rules(points)
    by_name = dict(results)
    hard_failed = [name for name in _IMPULSE_HARD_RULES if not by_name.get(name, False)]

    up = points[0].kind == "low"
    prices = [p.price for p in points]
    labels = ["P0", "P1", "P2", "P3", "P4", "P5"]

    diagnostics = [_start_diag(points, labels)]
    for name in hard_failed:
        explain = _IMPULSE_RULE_EXPLAIN.get(name)
        if explain:
            diagnostics.append(explain(prices, up))

    if hard_failed:
        return False, ElliottAnalysis(
            timeframe="",
            primary_scenario="NO_VALID_COUNT",
            confidence=0.0,
            wave_points=_wave_points(points, labels),
            invalidation_price=round(points[0].price, 6),
            bias="unknown",
            degree="unknown",
            rules_passed=[n for n, ok in results if ok],
            rules_failed=[n for n, ok in results if not ok],
            diagnostics=diagnostics,
        )

    soft_passed = sum(
        1 for name, ok in results if ok and name not in _IMPULSE_HARD_RULES
    )
    soft_total = len(results) - len(_IMPULSE_HARD_RULES)
    confidence = 60.0 + (40.0 * soft_passed / soft_total if soft_total else 0.0)

    p1, p4 = points[1].price, points[4].price
    wave1_len = abs(p1 - points[0].price)
    target = _target_zone(p4, wave1_len, up=up)

    return True, ElliottAnalysis(
        timeframe="",  # caller sets
        primary_scenario="IMPULSE_1_2_3_4_5",
        confidence=round(confidence, 1),
        wave_points=_wave_points(points, labels),
        invalidation_price=round(points[0].price, 6),
        target_zone=target,
        bias="REVERSAL_SHORT" if up else "REVERSAL_LONG",
        degree="unknown",
        rules_passed=[n for n, ok in results if ok],
        rules_failed=[n for n, ok in results if not ok],
        diagnostics=[diagnostics[0]],
    )


def _try_abc(points: list[Pivot]) -> tuple[bool, ElliottAnalysis]:
    """bkz. `_try_impulse` docstring — aynı desen, ABC için."""
    results = wave_rules.check_abc_rules(points)
    by_name = dict(results)
    hard_failed = [name for name in _ABC_HARD_RULES if not by_name.get(name, False)]

    down_correction = points[0].kind == "high"
    prices = [p.price for p in points]
    labels = ["P0", "A", "B", "C"]

    diagnostics = [_start_diag(points, labels)]
    for name in hard_failed:
        explain = _ABC_RULE_EXPLAIN.get(name)
        if explain:
            diagnostics.append(explain(prices, down_correction))

    if hard_failed:
        return False, ElliottAnalysis(
            timeframe="",
            primary_scenario="NO_VALID_COUNT",
            confidence=0.0,
            wave_points=_wave_points(points, labels),
            invalidation_price=round(points[0].price, 6),
            bias="unknown",
            degree="unknown",
            rules_passed=[n for n, ok in results if ok],
            rules_failed=[n for n, ok in results if not ok],
            diagnostics=diagnostics,
        )

    soft_passed = sum(1 for name, ok in results if ok and name not in _ABC_HARD_RULES)
    soft_total = len(results) - len(_ABC_HARD_RULES)
    confidence = 60.0 + (40.0 * soft_passed / soft_total if soft_total else 0.0)

    a_price, b_price = points[1].price, points[2].price
    a_len = abs(a_price - points[0].price)
    target = _target_zone(b_price, a_len, up=not down_correction)

    return True, ElliottAnalysis(
        timeframe="",
        primary_scenario="ABC_CORRECTION",
        confidence=round(confidence, 1),
        wave_points=_wave_points(points, labels),
        invalidation_price=round(points[0].price, 6),
        target_zone=target,
        bias="REVERSAL_LONG" if down_correction else "REVERSAL_SHORT",
        degree="unknown",
        rules_passed=[n for n, ok in results if ok],
        rules_failed=[n for n, ok in results if not ok],
        diagnostics=[diagnostics[0]],
    )


def analyze(
    bars: list,
    *,
    timeframe: str,
    pivot_left: int | None = None,
    pivot_right: int | None = None,
) -> ElliottAnalysis:
    """Deterministik Elliott senaryosu — NO_VALID_COUNT meşru bir sonuçtur.

    `pivot_left`/`pivot_right` verilmezse config'ten (`elliott.pivot_left/right`)
    okunur. Önce 6 noktalı impulse adayı denenir; geçersizse 4 noktalı ABC adayı
    denenir; ikisi de hard-rule'ları geçemezse NO_VALID_COUNT döner
    (uydurma senaryo yok — spec §10.3/§10.6).
    """
    if pivot_left is None or pivot_right is None:
        cfg_left, cfg_right = _default_pivot_window()
        pivot_left = pivot_left if pivot_left is not None else cfg_left
        pivot_right = pivot_right if pivot_right is not None else cfg_right

    rejected: list[ElliottAnalysis] = []

    impulse_pts = last_n_alternating(bars, 6, left=pivot_left, right=pivot_right)
    if impulse_pts:
        valid, result = _try_impulse(impulse_pts)
        if valid:
            return result.model_copy(update={"timeframe": timeframe})
        rejected.append(result)

    abc_pts = last_n_alternating(bars, 4, left=pivot_left, right=pivot_right)
    if abc_pts:
        valid, result = _try_abc(abc_pts)
        if valid:
            return result.model_copy(update={"timeframe": timeframe})
        rejected.append(result)

    if rejected:
        # Reddedilen denemelerin TAMAMININ açıklamasını birleştir — hangi
        # sayımın nereden başladığı ve hangi kuralın neye göre ihlal
        # edildiği uydurmasız, gerçek pivot değerleriyle gösterilir.
        combined_diag: list[str] = []
        for r in rejected:
            combined_diag.extend(r.diagnostics)
        best = rejected[0]
        return best.model_copy(update={"timeframe": timeframe, "diagnostics": combined_diag})

    return ElliottAnalysis(
        timeframe=timeframe,
        primary_scenario="NO_VALID_COUNT",
        confidence=0.0,
        bias="unknown",
        degree="unknown",
        diagnostics=["insufficient_pivots"],
    )


__all__ = ["analyze"]
