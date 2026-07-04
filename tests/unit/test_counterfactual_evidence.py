"""F5-1 — counterfactual (missed_opportunity) → ampirik kanıt bağlantısı testleri.

- resolutions(): yalnız resolve event'leri.
- build_table: counterfactual'lar AYRI kanalda (cf_by_tf); expired paydaya
  girmez; gerçek hücreler (cells/by_tf) counterfactual'la KİRLENMEZ.
- lookup: blend flag KAPALI (default) → bayt-aynı (cf verisi yok sayılır);
  AÇIK → yalnız gerçek kanıt yetersizken son-çare harman ("tf_blend_cf");
  gerçek kanıt yeterliyse harman devreye GİRMEZ.
- summary_viewmodel: by_timeframe cf_win_rate kanıtı.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import empirical_pwin as ep
from packages.learning import missed_opportunity as mo

_BLEND_ON = {"empirical_pwin": {"enabled": False, "min_samples": 5, "blend_counterfactual": True}}
_BLEND_OFF = {"empirical_pwin": {"enabled": False, "min_samples": 5, "blend_counterfactual": False}}


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


def test_blend_off_ignores_cf(ep_env) -> None:
    """Default: gerçek kanıt yetersiz + bol cf → yine None (bayt-aynı)."""
    with threshold_override(_BLEND_OFF):
        _write_table(ep_env, [_o("1h", "NEUTRAL", +1)], [_cf("1h", "missed_win")] * 10)
        assert ep.lookup("1h", "NEUTRAL") is None


def test_blend_on_last_resort_fallback(ep_env) -> None:
    with threshold_override(_BLEND_ON):
        # gerçek: 2 örnek (yetersiz, 1W/1L); cf: 4 örnek (3W/1L) → harman 6 ≥ 5
        _write_table(
            ep_env,
            [_o("1h", "NEUTRAL", +1), _o("1h", "NEUTRAL", -1)],
            [_cf("1h", "missed_win")] * 3 + [_cf("1h", "avoided_loss")],
        )
        hit = ep.lookup("1h", "NEUTRAL")
        assert hit is not None and hit.source == "tf_blend_cf"
        assert (hit.wins, hit.losses, hit.n) == (4, 2, 6)
        assert hit.p_win == pytest.approx(4 / 6, abs=1e-3)


def test_blend_on_prefers_actual_when_sufficient(ep_env) -> None:
    """Gerçek kanıt yeterliyse harman HİÇ devreye girmez (cf farklı olsa da)."""
    with threshold_override(_BLEND_ON):
        _write_table(
            ep_env,
            [_o("1h", "NEUTRAL", +1)] * 4 + [_o("1h", "NEUTRAL", -1)],  # 5 örnek, p=0.8
            [_cf("1h", "avoided_loss")] * 20,                            # cf tersini söylüyor
        )
        hit = ep.lookup("1h", "NEUTRAL")
        assert hit.source == "tf_regime" and hit.p_win == pytest.approx(0.8)


def test_blend_on_still_none_when_combined_insufficient(ep_env) -> None:
    with threshold_override(_BLEND_ON):
        _write_table(ep_env, [_o("1h", "NEUTRAL", +1)], [_cf("1h", "missed_win")])
        assert ep.lookup("1h", "NEUTRAL") is None  # 2 < 5 — sahte p yok


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
