"""Faz-A (EV kapısı) — per-hücre payoff EV hazırlık yüzeyi testleri.

- payoff_readiness(): hücre HER İKİ yönde de win_r_n/loss_r_n ≥ min_r_samples
  ise payoff_ready; aksi short_by = eşiğe kalan (iki yönün zayıfı). closest_cell
  = eşiğe en yakın hazır-olmayan. Tablo yoksa NO_DATA.
"""
from __future__ import annotations

import json

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import empirical_pwin as e

_CFG = {"ev_gate": {"min_r_samples": 8, "payoff_weighted": True}}


@pytest.fixture(autouse=True)
def table_path(tmp_path, monkeypatch):
    p = tmp_path / "empirical.json"
    monkeypatch.setenv("EMPIRICAL_PWIN_PATH", str(p))
    monkeypatch.setattr(e, "_CACHE", {})
    return p


def _write(cells):
    e._path().write_text(json.dumps({"cells": cells}), encoding="utf-8")


def test_ready_when_both_directions_meet_threshold():
    _write({"1d|NEUTRAL": {"win_r_n": 10, "loss_r_n": 9}})
    with threshold_override(_CFG):
        r = e.payoff_readiness()
    row = r["per_cell"][0]
    assert row["payoff_ready"] is True and row["short_by"] == 0
    assert r["ready_cells"] == ["1d|NEUTRAL"]
    assert r["closest_cell"] is None


def test_not_ready_uses_weaker_direction():
    # win_r_n eşiği geçti ama loss_r_n=6 → short_by = 8-6 = 2
    _write({"1d|NEUTRAL": {"win_r_n": 12, "loss_r_n": 6}})
    with threshold_override(_CFG):
        r = e.payoff_readiness()
    row = r["per_cell"][0]
    assert row["payoff_ready"] is False and row["short_by"] == 2
    assert r["ready_count"] == 0


def test_closest_cell_is_nearest_not_ready():
    _write({
        "15m|NEUTRAL": {"win_r_n": 7, "loss_r_n": 6},   # short 2
        "4h|OFFENSIVE": {"win_r_n": 1, "loss_r_n": 0},  # short 8
    })
    with threshold_override(_CFG):
        r = e.payoff_readiness()
    assert r["closest_cell"]["cell"] == "15m|NEUTRAL"
    assert r["closest_cell"]["short_by"] == 2


def test_no_table_is_no_data():
    with threshold_override(_CFG):
        r = e.payoff_readiness()
    assert r["status"] == "NO_DATA"
    assert r["per_cell"] == []


def test_shape_and_config_surfaced():
    _write({"1d|NEUTRAL": {"win_r_n": 10, "loss_r_n": 9}})
    with threshold_override(_CFG):
        r = e.payoff_readiness()
    assert r["min_r_samples"] == 8 and r["payoff_weighted"] is True
    assert r["shadow_only"] is True and r["cell_count"] == 1
