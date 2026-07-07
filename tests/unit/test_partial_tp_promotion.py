"""Faz-A (Çıkışlar) — partial-TP aktivasyon hazırlık kapısı testleri.

- evaluate(): üç kapı (min örnek + Wilson-alt>0.5 + net pozitif); kanıtsız/
  negatif → NOT_READY; hepsi tutunca READY.
- run(): READY ise governor owner-onay paketi sunulur (requested_change =
  partial_tp.enabled); NOT_READY ise paket YOK.
- summary(): readiness bloğu taşır (panel yüzeyi).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import partial_tp_shadow as ptp

_CFG = {"partial_tp": {"enabled": False, "promotion": {"min_evaluable": 4}}}


def _trade(pnl, shadow, r_hit=True):
    return SimpleNamespace(pnl_usd=pnl, ptp_shadow_pnl_usd=shadow, ptp_r_hit=r_hit)


def _state(trades):
    return SimpleNamespace(recent_trades=trades)


def test_not_ready_below_min_evaluable():
    st = _state([_trade(10, 20)] * 2)  # 2 < min_evaluable(4)
    with threshold_override(_CFG):
        r = ptp.evaluate(st)
    assert r["status"] == "NOT_READY"
    assert r["checks"]["evaluable"]["pass"] is False


def test_not_ready_when_uplift_negative():
    # yeterli örnek ama shadow gerçekten daha KÖTÜ (uplift negatif) → net_positive düşer
    st = _state([_trade(20, 10)] * 6)  # her uplift = -10
    with threshold_override(_CFG):
        r = ptp.evaluate(st)
    assert r["status"] == "NOT_READY"
    assert r["checks"]["net_positive"]["pass"] is False
    assert r["total_uplift_usd"] < 0


def test_not_ready_when_win_rate_not_disjoint():
    # net pozitif ama isabet 50/50 → Wilson alt sınırı 0.5'i geçmez
    st = _state([_trade(10, 40)] * 3 + [_trade(10, 5)] * 3)  # 3 kazan / 3 kaybet
    with threshold_override(_CFG):
        r = ptp.evaluate(st)
    assert r["checks"]["uplift_win_rate"]["pass"] is False
    assert r["status"] == "NOT_READY"


def test_ready_when_all_gates_pass():
    st = _state([_trade(10, 30)] * 12)  # 12/12 uplift+, toplam pozitif
    with threshold_override(_CFG):
        r = ptp.evaluate(st)
    assert r["checks"]["evaluable"]["pass"] is True
    assert r["checks"]["uplift_win_rate"]["pass"] is True
    assert r["checks"]["net_positive"]["pass"] is True
    assert r["status"] == "READY"


def test_run_submits_package_only_when_ready(monkeypatch):
    calls = []
    monkeypatch.setattr(ptp.rail, "submit_enable",
                        lambda **kw: calls.append(kw) or {"proposal_id": "p1"})

    with threshold_override(_CFG):
        ready = ptp.run(_state([_trade(10, 30)] * 12))
        not_ready = ptp.run(_state([_trade(10, 5)] * 12))  # uplift negatif

    assert ready["status"] == "READY" and ready["proposal_id"] == "p1"
    assert not_ready["status"] == "NOT_READY"
    assert len(calls) == 1
    assert calls[0]["requested_change"] == {"partial_tp.enabled": True}
    assert calls[0]["source"] == "partial_tp_shadow"


def test_summary_carries_readiness():
    st = _state([_trade(10, 30)] * 5)
    with threshold_override(_CFG):
        s = ptp.summary(st)
    assert "readiness" in s and s["readiness"]["status"] in ("READY", "NOT_READY")
    assert s["evaluable_trades"] == 5
    assert s["uplift_usd"] == pytest.approx(100.0)  # (30-10)*5
