"""Çıkış stop-verim backtest'i testleri (SALT-ANALİZ).

- simulate(): sabit SL vurulunca −sl_mult R; TP vurulunca +TP_RR; dar trail kârı
  daha çok kilitler; partial_tp trigger'da frac kapatır.
- compute(): entry ızgarasını tarar, marginal/per_tf_best üretir; en verimli config
  avg_r'ye göre sıralanır; TF kırılımı doğru.
- viewmodel(): artifact yok → NO_DATA; varken shadow_only + best_configs.
"""
from __future__ import annotations

import json
from types import SimpleNamespace as N

import pytest

from packages.learning import exit_backtest as eb


def _bar(hi, lo, c):
    return N(high=hi, low=lo, close=c, ts=None)


@pytest.fixture(autouse=True)
def art_path(tmp_path, monkeypatch):
    monkeypatch.setenv("EXIT_BACKTEST_PATH", str(tmp_path / "eb.json"))
    return tmp_path


# ── simulate ──────────────────────────────────────────────────────────────────

def test_simulate_fixed_stop_hit():
    # long, entry 100, unit 2 (1R=2). Bar dibi 95 → SL(1.0R=98) vurulur → −1R.
    fwd = [_bar(101, 95, 96)]
    r = eb.simulate(100.0, 2.0, True, fwd, sl_mult=1.0, trail_act=99, trail_dist=1.0,
                    ptp_trigger=999, ptp_frac=0.0)
    assert r == pytest.approx(-1.0)


def test_simulate_tp_hit():
    # tepe 106 = +3R (TP_RR) → +3R
    fwd = [_bar(107, 100, 106)]
    r = eb.simulate(100.0, 2.0, True, fwd, sl_mult=1.0, trail_act=99, trail_dist=1.0,
                    ptp_trigger=999, ptp_frac=0.0)
    assert r == pytest.approx(eb.TP_RR)


def test_simulate_tight_trail_locks_more_than_loose():
    # kâra çıkıp geri veren yol: dar trail (0.5R) gevşekten (1.5R) daha çok kilitler
    fwd = [_bar(105, 100, 104), _bar(105, 98, 99)]  # +2.5R tepe, sonra geri
    tight = eb.simulate(100.0, 2.0, True, fwd, sl_mult=2.0, trail_act=1.0,
                        trail_dist=0.5, ptp_trigger=999, ptp_frac=0.0)
    loose = eb.simulate(100.0, 2.0, True, fwd, sl_mult=2.0, trail_act=1.0,
                        trail_dist=1.5, ptp_trigger=999, ptp_frac=0.0)
    assert tight > loose


def test_simulate_short_symmetry():
    # short, entry 100, unit 2. Bar tepesi 105 → SL(1.0R=102) vurulur → −1R.
    fwd = [_bar(105, 99, 104)]
    r = eb.simulate(100.0, 2.0, False, fwd, sl_mult=1.0, trail_act=99, trail_dist=1.0,
                    ptp_trigger=999, ptp_frac=0.0)
    assert r == pytest.approx(-1.0)


# ── compute ───────────────────────────────────────────────────────────────────

def _up_entries(tf="1h", n=4):
    fwd = [_bar(102, 99, 101), _bar(106, 100, 105), _bar(112, 104, 111),
           _bar(118, 109, 117), _bar(124, 115, 123)]
    return [(tf, 100.0, 2.0, True, fwd)] * n


def test_compute_produces_ranked_report():
    r = eb.compute(entries=_up_entries("1h", 3) + _up_entries("4h", 2))
    assert r["entry_count"] == 5
    assert r["tf_counts"] == {"1h": 3, "4h": 2}
    # en iyi config avg_r'ye göre başta
    assert r["best_configs"][0]["avg_r"] >= r["best_configs"][-1]["avg_r"]
    # marginal tüm ızgara boyutlarını taşır
    assert set(r["marginal"]["trail_dist"].keys()) == {str(g) for g in eb.TRAIL_DIST_GRID}
    assert "1h" in r["per_tf_best"] and "4h" in r["per_tf_best"]


def test_compute_tight_trail_wins_on_giveback_path():
    # kâra çıkıp geri veren yol → marjinal olarak dar trail (0.5) en yüksek olmalı
    fwd = [_bar(106, 100, 105), _bar(106, 99, 100), _bar(103, 98, 99)]
    ents = [("1h", 100.0, 2.0, True, fwd)] * 6
    r = eb.compute(entries=ents)
    m = r["marginal"]["trail_dist"]
    assert m["0.5"] >= max(m["0.75"], m["1.0"], m["1.5"])


# ── viewmodel + run_if_due ────────────────────────────────────────────────────

def test_viewmodel_no_data():
    assert eb.viewmodel()["status"] == "NO_DATA"


def test_run_if_due_writes_then_skips(monkeypatch):
    monkeypatch.setattr(eb, "_build_entries", lambda: _up_entries("1h", 4))
    first = eb.run_if_due()
    assert first["status"] == "OK" and first["entries"] == 4
    vm = eb.viewmodel()
    assert vm["status"] == "OK" and vm["shadow_only"] is True and vm["best_configs"]
    # taze artifact → ikinci çağrı SKIP
    assert eb.run_if_due()["status"] == "SKIP_FRESH"


def test_run_if_due_stale_artifact_recomputes(monkeypatch, tmp_path):
    monkeypatch.setattr(eb, "_build_entries", lambda: _up_entries("1h", 4))
    monkeypatch.setenv("EXIT_BACKTEST_INTERVAL_SEC", "0")  # her zaman bayat
    eb.run_if_due()
    # interval 0 → taze sayılmaz → yeniden üretir
    assert eb.run_if_due()["status"] == "OK"


def test_artifact_is_valid_json(monkeypatch):
    monkeypatch.setattr(eb, "_build_entries", lambda: _up_entries("1h", 4))
    eb.run_if_due()
    data = json.loads(eb._path().read_text(encoding="utf-8"))
    assert data["engine"] == "exit_backtest_v1"
