"""F5 (21 Kasım 2026) — alt risk modüllerinin ortak iskeleti: davranış eskisiyle aynı."""
from __future__ import annotations

from packages.risk import derivatives_risk as dr
from packages.risk import options_risk as orisk
from packages.risk import volatility_risk as vr


def test_zero_weight_resets_level_and_keeps_extra_fields():
    v = orisk.OptionsVerdict(level="CAUTION", size_factor=0.5, reason="x", regime="RICH_VOL", evidence=["e"])
    assert orisk.apply_timeframe(v, 0.0) == orisk.OptionsVerdict(
        regime="RICH_VOL", reason="Options etkisi bu timeframe'de devre dışı.")
    d = dr.DerivativesVerdict(level="NO_POSITION_INCREASE", size_factor=0.0, block=True, reason="y", evidence=["e"])
    assert dr.apply_timeframe(d, 0.0) == dr.DerivativesVerdict(reason="Türev etkisi bu timeframe'de devre dışı.")


def test_low_weight_softens_block_and_full_weight_keeps_it():
    d = dr.DerivativesVerdict(level="NO_POSITION_INCREASE", size_factor=0.0, block=True, reason="y", evidence=["e"])
    out = dr.apply_timeframe(d, 0.5)
    assert (out.level, out.size_factor, out.block, out.reason, out.evidence) == ("CAUTION", 0.5, False, "y (tf×0.5)", ["e"])
    v = vr.VolatilityVerdict(level="NO_POSITION_INCREASE", size_factor=0.0, block=True, reason="z")
    full = vr.apply_timeframe(v, 1.0)
    assert (full.level, full.size_factor, full.block, full.reason) == ("NO_POSITION_INCREASE", 0.0, True, "z")
    none = vr.VolatilityVerdict()
    assert vr.apply_timeframe(none, 0.3) is none


def test_size_factors_only_shrink():
    for table in (dr._LEVEL_SIZE_FACTOR, vr._LEVEL_SIZE_FACTOR, orisk._LEVEL_SIZE_FACTOR):
        assert all(0.0 <= f <= 1.0 for f in table.values())
        assert table == {"NONE": 1.0, "WATCH": 1.0, "CAUTION": 0.5, "NO_POSITION_INCREASE": 0.0}
