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


def _target_zone(anchor: float, length: float, *, up: bool) -> tuple[float, float]:
    proj = _fib_projection()
    lo_ratio, hi_ratio = proj[0], proj[-1]
    if up:
        return (round(anchor + lo_ratio * length, 6), round(anchor + hi_ratio * length, 6))
    return (round(anchor - hi_ratio * length, 6), round(anchor - lo_ratio * length, 6))


def _try_impulse(points: list[Pivot]) -> ElliottAnalysis | None:
    results = wave_rules.check_impulse_rules(points)
    by_name = dict(results)
    hard_failed = [name for name in _IMPULSE_HARD_RULES if not by_name.get(name, False)]
    if hard_failed:
        return None

    soft_passed = sum(
        1 for name, ok in results if ok and name not in _IMPULSE_HARD_RULES
    )
    soft_total = len(results) - len(_IMPULSE_HARD_RULES)
    confidence = 60.0 + (40.0 * soft_passed / soft_total if soft_total else 0.0)

    up = points[0].kind == "low"
    p1, p4 = points[1].price, points[4].price
    wave1_len = abs(p1 - points[0].price)
    target = _target_zone(p4, wave1_len, up=up)

    return ElliottAnalysis(
        timeframe="",  # caller sets
        primary_scenario="IMPULSE_1_2_3_4_5",
        confidence=round(confidence, 1),
        wave_points=_wave_points(points, ["P0", "P1", "P2", "P3", "P4", "P5"]),
        invalidation_price=round(points[0].price, 6),
        target_zone=target,
        bias="REVERSAL_SHORT" if up else "REVERSAL_LONG",
        degree="unknown",
        rules_passed=[n for n, ok in results if ok],
        rules_failed=[n for n, ok in results if not ok],
        diagnostics=[],
    )


def _try_abc(points: list[Pivot]) -> ElliottAnalysis | None:
    results = wave_rules.check_abc_rules(points)
    by_name = dict(results)
    hard_failed = [name for name in _ABC_HARD_RULES if not by_name.get(name, False)]
    if hard_failed:
        return None

    soft_passed = sum(1 for name, ok in results if ok and name not in _ABC_HARD_RULES)
    soft_total = len(results) - len(_ABC_HARD_RULES)
    confidence = 60.0 + (40.0 * soft_passed / soft_total if soft_total else 0.0)

    down_correction = points[0].kind == "high"
    a_price, b_price, c_price = points[1].price, points[2].price, points[3].price
    a_len = abs(a_price - points[0].price)
    target = _target_zone(b_price, a_len, up=not down_correction)

    return ElliottAnalysis(
        timeframe="",
        primary_scenario="ABC_CORRECTION",
        confidence=round(confidence, 1),
        wave_points=_wave_points(points, ["P0", "A", "B", "C"]),
        invalidation_price=round(points[0].price, 6),
        target_zone=target,
        bias="REVERSAL_LONG" if down_correction else "REVERSAL_SHORT",
        degree="unknown",
        rules_passed=[n for n, ok in results if ok],
        rules_failed=[n for n, ok in results if not ok],
        diagnostics=[],
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

    impulse_pts = last_n_alternating(bars, 6, left=pivot_left, right=pivot_right)
    if impulse_pts:
        result = _try_impulse(impulse_pts)
        if result is not None:
            return result.model_copy(update={"timeframe": timeframe})

    abc_pts = last_n_alternating(bars, 4, left=pivot_left, right=pivot_right)
    if abc_pts:
        result = _try_abc(abc_pts)
        if result is not None:
            return result.model_copy(update={"timeframe": timeframe})

    diag = []
    if not impulse_pts and not abc_pts:
        diag.append("insufficient_pivots")
    return ElliottAnalysis(
        timeframe=timeframe,
        primary_scenario="NO_VALID_COUNT",
        confidence=0.0,
        bias="unknown",
        degree="unknown",
        diagnostics=diag or ["hard_rules_failed"],
    )


__all__ = ["analyze"]
