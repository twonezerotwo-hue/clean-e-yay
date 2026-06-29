"""Elliott hard rules — saf, deterministik kural kontrolleri.

Spec §10.4 (Elliott hard rules): "Wave 2 Wave 1 başlangıcını geçmemeli",
"Wave 3 en kısa dalga olmamalı", "Wave 4 Wave 1 alanına girmemeli". Bu modül
6 alternatif pivottan (P0..P5, uptrend: low-high-low-high-low-high) bu
kuralları kontrol eder ve geçen/kalan kural listesini döner — uydurma
"geçti" yok, her kural açıkça test edilir.
"""
from __future__ import annotations

from packages.elliott.pivots import Pivot

ImpulseRuleResult = tuple[str, bool]


def _is_uptrend_impulse(points: list[Pivot]) -> bool:
    return points[0].kind == "low"


def check_impulse_rules(points: list[Pivot]) -> list[ImpulseRuleResult]:
    """6 noktalı (P0..P5) impulse aday dizisi için hard-rule kontrolleri.

    `points` tam 6 alternatif pivot olmalı (çağıran taraf garanti eder).
    Uptrend (low-high-low-high-low-high) veya downtrend (ayna) kabul edilir.
    """
    if len(points) != 6:
        return [("sequence_length", False)]

    up = _is_uptrend_impulse(points)
    p0, p1, p2, p3, p4, p5 = (p.price for p in points)

    wave1 = abs(p1 - p0)
    wave3 = abs(p3 - p2)
    wave5 = abs(p5 - p4)

    if up:
        r1 = p2 > p0  # wave2, wave1 başlangıcını (P0) geçmedi
        r3_no_overlap = p4 > p1  # wave4, wave1 alanına (P1'in altına) girmedi
        r4_extends = p3 > p1  # wave3 yeni high yaptı
    else:
        r1 = p2 < p0
        r3_no_overlap = p4 < p1
        r4_extends = p3 < p1

    r2_not_shortest = not (wave3 < wave1 and wave3 < wave5) if wave1 and wave5 else wave3 > 0

    return [
        ("wave2_no_breach_wave0", bool(r1)),
        ("wave3_not_shortest", bool(r2_not_shortest)),
        ("wave4_no_overlap_wave1", bool(r3_no_overlap)),
        ("wave3_extends_wave1", bool(r4_extends)),
    ]


def check_abc_rules(points: list[Pivot]) -> list[ImpulseRuleResult]:
    """4 noktalı (P0-A-B-C) zigzag correction aday dizisi için kontroller.

    Spec §10.4: "ABC yapısı oranlı olmalı", "C wave A ile uyumlu extension
    üretmeli", "B wave makul retracement alanında kalmalı".
    """
    if len(points) != 4:
        return [("sequence_length", False)]

    down_correction = points[1].kind in ("low",) and points[0].kind == "high"
    p0, a, b, c = (p.price for p in points)

    if down_correction:
        r1_a_below_p0 = a < p0
        r2_b_below_p0 = b < p0  # B, P0'ı geçmedi (basit zigzag — complex değil)
        r3_c_extends_a = c < a  # C, A'nın ötesine uzandı
    else:
        r1_a_below_p0 = a > p0
        r2_b_below_p0 = b > p0
        r3_c_extends_a = c > a

    return [
        ("a_extends_from_p0", bool(r1_a_below_p0)),
        ("b_within_p0_retracement", bool(r2_b_below_p0)),
        ("c_extends_beyond_a", bool(r3_c_extends_a)),
    ]


def confidence_from_rules(results: list[ImpulseRuleResult]) -> float:
    if not results:
        return 0.0
    passed = sum(1 for _, ok in results if ok)
    return round(passed / len(results) * 100.0, 1)


__all__ = ["check_abc_rules", "check_impulse_rules", "confidence_from_rules"]
