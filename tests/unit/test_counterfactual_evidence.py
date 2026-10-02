"""F5-1 — counterfactual (missed_opportunity) → ampirik kanıt bağlantısı testleri.

- resolutions(): yalnız resolve event'leri.
- build_table: counterfactual'lar AYRI kanalda (cf_by_tf); expired paydaya
  girmez; gerçek hücreler (cells/by_tf) counterfactual'la KİRLENMEZ.
- lookup: counterfactual verisi p(win)'e harmanlanmaz (yalnız gözlem kanalı).
- summary_viewmodel: by_timeframe cf_win_rate kanıtı.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import empirical_pwin as ep
from packages.learning import missed_opportunity as mo

_CFG = {"empirical_pwin": {"enabled": False, "min_samples": 5}}


def _o(tf: str, regime: str, pnl: float):
    return SimpleNamespace(timeframe=tf, regime=regime, pnl=pnl, data_verified=True)


def _cf(tf: str, outcome: str) -> dict:
    return {"event": "resolve", "timeframe": tf, "outcome": outcome}


@pytest.fixture
def ep_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRICAL_PWIN_PATH", str(tmp_path / "empirical_pwin.json"))
    monkeypatch.setenv("MISSED_OPP_LOG_PATH", str(tmp_path / "missed_opp.jsonl"))
    return tmp_path


# ------------------------------ resolutions ----------------------------------

def test_resolutions_filters_resolve_events(ep_env) -> None:
    p = ep_env / "missed_opp.jsonl"
    rows = [
        {"event": "track_open", "id": "a"},
        {"event": "resolve", "id": "a", "outcome": "missed_win", "timeframe": "1h"},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    res = mo.resolutions()
    assert len(res) == 1 and res[0]["outcome"] == "missed_win"
    # dosya yok → boş (crash yok)
    p.unlink()
    assert mo.resolutions() == []


# ------------------------------- build_table ---------------------------------

def test_cf_channel_separate_from_actual() -> None:
    outcomes = [_o("1h", "NEUTRAL", +1), _o("1h", "NEUTRAL", -1)]
    cfs = [_cf("1h", "missed_win"), _cf("1h", "missed_win"),
           _cf("1h", "avoided_loss"), _cf("1h", "expired")]
    t = ep.build_table(outcomes, counterfactuals=cfs)
    # gerçek kanal counterfactual'dan ETKİLENMEDİ
    assert t["by_tf"]["1h"]["n"] == 2
    assert t["cells"]["1h|NEUTRAL"]["n"] == 2
    # cf kanalı: 2 win + 1 loss (expired paydaya girmedi). F5-3: cf'in gerçekleşen
    # R'si yok (paper açılmadı) → R alanları None/0.
    cf = t["cf_by_tf"]["1h"]
    assert (cf["wins"], cf["losses"], cf["n"]) == (2, 1, 3)
    assert cf["p_win"] == pytest.approx(2 / 3, abs=1e-3)
    assert cf["avg_win_r"] is None and cf["avg_loss_r"] is None


# --------------------------------- lookup ------------------------------------

def _write_table(ep_env, outcomes, cfs) -> None:
    (ep_env / "empirical_pwin.json").write_text(
        json.dumps(ep.build_table(outcomes, counterfactuals=cfs)), encoding="utf-8"
    )


def test_lookup_ignores_cf(ep_env) -> None:
    """Gerçek kanıt yetersiz + bol cf → yine None (cf yalnız gözlem)."""
    with threshold_override(_CFG):
        _write_table(ep_env, [_o("1h", "NEUTRAL", +1)], [_cf("1h", "missed_win")] * 10)
        assert ep.lookup("1h", "NEUTRAL") is None


# ---------------------------- summary_viewmodel ------------------------------

def test_summary_by_timeframe_evidence(ep_env) -> None:
    p = ep_env / "missed_opp.jsonl"
    rows = [
        {"event": "resolve", "id": "a", "outcome": "missed_win", "timeframe": "1h"},
        {"event": "resolve", "id": "b", "outcome": "missed_win", "timeframe": "1h"},
        {"event": "resolve", "id": "c", "outcome": "avoided_loss", "timeframe": "1h"},
        {"event": "resolve", "id": "d", "outcome": "expired", "timeframe": "1h"},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    vm = mo.summary_viewmodel()
    bt = vm["by_timeframe"]["1h"]
    assert (bt["missed_win"], bt["avoided_loss"], bt["expired"]) == (2, 1, 1)
    assert bt["n"] == 3 and bt["cf_win_rate"] == pytest.approx(2 / 3, abs=1e-3)
