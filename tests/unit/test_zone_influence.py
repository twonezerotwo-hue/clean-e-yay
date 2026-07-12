"""Bölge onay defteri + canlı etki dikişi testleri (owner kararı 2026-07-12).

- zone_approval: varsayılan ONAYLI; iptal → iptal; tekrar onay → onaylı (en
  yeni kazanır); bant örtüşmesiyle eşleşme (milim kaymış bölge aynı sayılır).
- zone_influence.adjust_targets: TP bölge önüne, SL bölge arkasına; RR tabanı
  altında TP'ye dokunulmaz; bölge yoksa değişiklik yok.
- trade_economics dikişi: flag KAPALI (test baseline) → SL/TP BAYT-AYNI;
  açıkken onaylı bölge SL/TP'yi taşır; owner manuel işlemi MUAF.
"""
from __future__ import annotations

import pytest

from packages.learning import zone_approval
from packages.risk import trade_economics as te
from packages.risk import zone_influence

# ---------------------------------------------------------------- onay defteri

def _use_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("ZONE_VERDICTS_PATH", str(tmp_path / "verdicts.json"))


def test_default_verdict_is_approved(tmp_path, monkeypatch):
    """Defterde kayıt yokken bölge ONAYLI (owner: iptal edilmedikçe onaylı)."""
    _use_ledger(tmp_path, monkeypatch)
    assert zone_approval.verdict_for("BTCUSD", 50100, 52000) == "onayli"


def test_cancel_then_reapprove_latest_wins(tmp_path, monkeypatch):
    _use_ledger(tmp_path, monkeypatch)
    zone_approval.record("BTCUSD", 50100, 52000, "iptal", note="saçma bölge")
    assert zone_approval.verdict_for("BTCUSD", 50100, 52000) == "iptal"
    zone_approval.record("BTCUSD", 50100, 52000, "onay")
    assert zone_approval.verdict_for("BTCUSD", 50100, 52000) == "onayli"
    assert len(zone_approval.history("BTCUSD")) == 2


def test_overlap_matching_survives_drift(tmp_path, monkeypatch):
    """Önerici bölgeyi milim farkla yeniden üretse de iptal uygulanır."""
    _use_ledger(tmp_path, monkeypatch)
    zone_approval.record("TLT", 80.97, 82.83, "iptal")
    assert zone_approval.verdict_for("TLT", 81.10, 82.95) == "iptal"   # örtüşüyor
    assert zone_approval.verdict_for("TLT", 89.5, 91.7) == "onayli"    # uzak bölge
    assert zone_approval.verdict_for("DXY", 80.97, 82.83) == "onayli"  # başka sembol


def test_record_validates_action(tmp_path, monkeypatch):
    _use_ledger(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        zone_approval.record("BTCUSD", 50100, 52000, "belki")


# ------------------------------------------------------------ etki matematiği

_CFG = {"enabled": True, "pad_pct": 0.005, "min_rr_after": 0.8}


def test_adjust_long_tp_pulled_in_front_of_zone(monkeypatch):
    """LONG: giriş-TP arasındaki onaylı bölge → TP bölgenin alt kenarına."""
    monkeypatch.setattr(zone_influence, "_cfg", lambda: dict(_CFG))
    sl, tp, notes = zone_influence.adjust_targets(
        "X", "long", 100.0, 95.0, 120.0,
        zones=[{"low": 110.0, "high": 115.0, "confluence": 3}])
    assert tp == 110.0 and sl == 95.0
    assert any(n.startswith("zone_tp_front") for n in notes)


def test_adjust_long_tp_skip_when_rr_too_low(monkeypatch):
    """Bölge girişe çok yakınsa (RR tabanı altı) TP'ye DOKUNULMAZ."""
    monkeypatch.setattr(zone_influence, "_cfg", lambda: dict(_CFG))
    _sl, tp, notes = zone_influence.adjust_targets(
        "X", "long", 100.0, 95.0, 120.0,
        zones=[{"low": 101.0, "high": 104.0, "confluence": 2}])
    assert tp == 120.0
    assert "zone_tp_skip_rr" in notes


def test_adjust_long_sl_moved_behind_zone(monkeypatch):
    """SL bölge içine denk geliyorsa alt kenarın pad altına taşınır."""
    monkeypatch.setattr(zone_influence, "_cfg", lambda: dict(_CFG))
    sl, _tp, notes = zone_influence.adjust_targets(
        "X", "long", 100.0, 95.0, 120.0,
        zones=[{"low": 94.0, "high": 97.0, "confluence": 4}])
    assert sl == pytest.approx(94.0 * 0.995)
    assert any(n.startswith("zone_sl_behind") for n in notes)


def test_adjust_short_mirror(monkeypatch):
    monkeypatch.setattr(zone_influence, "_cfg", lambda: dict(_CFG))
    sl, tp, notes = zone_influence.adjust_targets(
        "X", "short", 100.0, 105.0, 80.0,
        zones=[{"low": 85.0, "high": 88.0, "confluence": 3},
               {"low": 103.0, "high": 106.0, "confluence": 2}])
    assert tp == 88.0                                # bölge önünde kâr
    assert sl == pytest.approx(106.0 * 1.005)        # bölge arkasında stop
    assert len([n for n in notes if n.startswith("zone_")]) == 2


def test_adjust_no_zones_no_change(monkeypatch):
    monkeypatch.setattr(zone_influence, "_cfg", lambda: dict(_CFG))
    sl, tp, notes = zone_influence.adjust_targets(
        "X", "long", 100.0, 95.0, 120.0, zones=[])
    assert (sl, tp, notes) == (95.0, 120.0, [])


# --------------------------------------------------------- canlı dikiş (seam)

_ZONE = [{"low": 104.0, "high": 106.0, "confluence": 5}]


def test_targets_byte_identical_when_flag_off(monkeypatch):
    """Flag KAPALI (test baseline): onaylı bölge VARKEN bile SL/TP bayt-aynı."""
    monkeypatch.setattr(zone_influence, "approved_zones", lambda s: list(_ZONE))
    t = te.compute_fixed_targets("BTCUSD", "long", 100.0, predicted_confidence=0.7)
    assert not [n for n in t.notes if n.startswith("zone_")]
    t2 = te.compute_tf_targets("BTCUSD", "long", 100.0, timeframe="4h",
                               atr=2.0, predicted_confidence=0.7)
    assert not [n for n in t2.notes if n.startswith("zone_")]


def test_targets_adjusted_when_flag_on(monkeypatch):
    """Flag AÇIK + onaylı bölge giriş-TP arasında → TP bölge önüne çekilir,
    türetilen rr/sl_distance tutarlı güncellenir."""
    monkeypatch.setattr(zone_influence, "_cfg", lambda: dict(_CFG))
    monkeypatch.setattr(zone_influence, "approved_zones", lambda s: list(_ZONE))
    base = te.compute_tf_targets("BTCUSD", "long", 100.0, timeframe="4h",
                                 atr=2.0, predicted_confidence=0.7)
    # baseline TP bölgenin üstünde olmalı ki etki ölçülebilsin
    assert base.tp > 104.0 or any(n.startswith("zone_") for n in base.notes)
    if any(n.startswith("zone_tp_front") for n in base.notes):
        assert base.tp == pytest.approx(104.0)
        assert base.rr == pytest.approx((base.tp - 100.0) / base.sl_distance, abs=1e-3)


def test_manual_trades_exempt(monkeypatch):
    """Owner manuel işlemi MUAF: flag açıkken bile SL/TP'ye dokunulmaz."""
    monkeypatch.setattr(zone_influence, "_cfg", lambda: dict(_CFG))
    monkeypatch.setattr(zone_influence, "approved_zones", lambda s: list(_ZONE))
    t = te.compute_fixed_targets("BTCUSD", "long", 100.0, manual=True)
    assert not [n for n in t.notes if n.startswith("zone_")]


def test_cancelled_zone_not_in_approved(tmp_path, monkeypatch):
    """approved_zones: owner'ın iptal ettiği bölge listeden düşer."""
    _use_ledger(tmp_path, monkeypatch)
    art = {"assets": [{"symbol": "TLT", "zones": [
        {"low": 80.97, "high": 82.83, "confluence": 5},
        {"low": 89.53, "high": 91.72, "confluence": 2},
    ]}]}
    from packages.learning import zone_proposer
    monkeypatch.setattr(zone_proposer, "_load", lambda: art)
    zone_approval.record("TLT", 80.97, 82.83, "iptal")
    zs = zone_influence.approved_zones("TLT")
    assert [z["low"] for z in zs] == [89.53]
