"""F4-2 — ampirik p(win) (TF+rejim hit-rate → EV/Kelly) testleri.

- build_table: yalnız verified; başabaş paydaya girmez (F1-2); tf|rejim + tf.
- lookup: min_samples altı hücre DÖNMEZ (sahte p yok); hiyerarşi tf|rejim → tf;
  artifact yok/bozuk → None.
- Karar motoru: flag KAPALI (default) → EV/Kelly cal_conf ile (bayt-aynı),
  ampirik değerler SALT-GÖZLEM alanlarında; AÇIK → EV ampirik p ile.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import empirical_pwin as ep

_ON = {"empirical_pwin": {"enabled": True, "min_samples": 5}}
_OFF_MIN5 = {"empirical_pwin": {"enabled": False, "min_samples": 5}}


def _o(tf: str, regime: str, pnl: float, verified: bool = True, r_multiple=None):
    return SimpleNamespace(
        timeframe=tf, regime=regime, pnl=pnl, data_verified=verified, r_multiple=r_multiple
    )


@pytest.fixture
def ep_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRICAL_PWIN_PATH", str(tmp_path / "empirical_pwin.json"))
    return tmp_path


# ------------------------------- build_table ---------------------------------

def test_build_table_counts_and_filters() -> None:
    outcomes = [
        _o("4h", "NEUTRAL", +10), _o("4h", "NEUTRAL", +5), _o("4h", "NEUTRAL", -3),
        _o("4h", "NEUTRAL", 0.0),          # başabaş → paydaya girmez (F1-2)
        _o("4h", "NEUTRAL", +7, verified=False),  # unverified → girmez
        _o("4h", "OFFENSIVE", -2),
        _o("1d", "NEUTRAL", +1),
    ]
    t = ep.build_table(outcomes)
    cell = t["cells"]["4h|NEUTRAL"]
    assert (cell["wins"], cell["losses"], cell["n"]) == (2, 1, 3)
    assert cell["p_win"] == pytest.approx(2 / 3, abs=1e-4)
    assert t["by_tf"]["4h"]["n"] == 4  # NEUTRAL 3 + OFFENSIVE 1
    assert t["cells"]["1d|NEUTRAL"]["p_win"] == 1.0
    assert t["cell_count"] == 3


# --------------------- F5-3: ayrık gerçekleşen R (payoff) ---------------------

def test_build_table_separates_win_and_loss_r() -> None:
    # 2 kazanç (+1.5R, +0.5R → avg +1.0R), 2 kayıp (−1.0R, −1.0R → avg 1.0R mag)
    outcomes = [
        _o("4h", "NEUTRAL", +10, r_multiple=1.5),
        _o("4h", "NEUTRAL", +5, r_multiple=0.5),
        _o("4h", "NEUTRAL", -3, r_multiple=-1.0),
        _o("4h", "NEUTRAL", -3, r_multiple=-1.0),
        _o("4h", "NEUTRAL", +7, r_multiple=None),  # R yok → magnitüde girmez, wins'e girer
    ]
    cell = ep.build_table(outcomes)["cells"]["4h|NEUTRAL"]
    assert cell["avg_win_r"] == pytest.approx(1.0)   # (1.5+0.5)/2 — R'siz kazanç hariç
    assert cell["avg_loss_r"] == pytest.approx(1.0)  # kayıp magnitüdü
    assert (cell["win_r_n"], cell["loss_r_n"]) == (2, 2)


def test_build_table_r_none_when_no_r_data() -> None:
    outcomes = [_o("1d", "NEUTRAL", +1), _o("1d", "NEUTRAL", -1)]  # r_multiple None
    cell = ep.build_table(outcomes)["cells"]["1d|NEUTRAL"]
    assert cell["avg_win_r"] is None and cell["avg_loss_r"] is None


def test_lookup_carries_r_stats(ep_env) -> None:
    (ep_env / "empirical_pwin.json").write_text(
        json.dumps({
            "cells": {"4h|NEUTRAL": {
                "p_win": 0.55, "wins": 11, "losses": 9, "n": 20,
                "avg_win_r": 0.8, "avg_loss_r": 1.1, "win_r_n": 11, "loss_r_n": 9,
            }},
            "by_tf": {},
        }),
        encoding="utf-8",
    )
    with threshold_override(_OFF_MIN5):
        hit = ep.lookup("4h", "NEUTRAL")
    assert hit is not None
    assert hit.avg_win_r == pytest.approx(0.8) and hit.avg_loss_r == pytest.approx(1.1)


def test_lookup_r_stats_none_for_legacy_cell(ep_env) -> None:
    # R alanları olmayan eski artifact → None (crash yok)
    _write(
        ep_env,
        cells={"4h|NEUTRAL": {"p_win": 0.55, "wins": 11, "losses": 9, "n": 20}},
        by_tf={},
    )
    with threshold_override(_OFF_MIN5):
        hit = ep.lookup("4h", "NEUTRAL")
    assert hit is not None and hit.avg_win_r is None and hit.avg_loss_r is None


# --------------------------------- lookup ------------------------------------

def _write(tmp_path, cells: dict, by_tf: dict) -> None:
    (tmp_path / "empirical_pwin.json").write_text(
        json.dumps({"cells": cells, "by_tf": by_tf}), encoding="utf-8"
    )


def test_lookup_hierarchy_and_min_samples(ep_env) -> None:
    _write(
        ep_env,
        cells={"4h|NEUTRAL": {"p_win": 0.60, "wins": 6, "losses": 4, "n": 10},
               "1h|NEUTRAL": {"p_win": 1.0, "wins": 2, "losses": 0, "n": 2}},
        by_tf={"4h": {"p_win": 0.55, "wins": 11, "losses": 9, "n": 20},
               "1h": {"p_win": 0.58, "wins": 7, "losses": 5, "n": 12}},
    )
    with threshold_override(_OFF_MIN5):
        hit = ep.lookup("4h", "NEUTRAL")
        assert hit is not None and hit.source == "tf_regime" and hit.p_win == 0.60
        # rejim hücresi 2 örnek < 5 → TF geneline düşer
        fb = ep.lookup("1h", "NEUTRAL")
        assert fb is not None and fb.source == "tf" and fb.p_win == 0.58
        # hiç kanıt yok → None
        assert ep.lookup("15m", "CRISIS") is None


def test_lookup_missing_or_corrupt_artifact_returns_none(ep_env) -> None:
    assert ep.lookup("4h", "NEUTRAL") is None  # dosya yok
    (ep_env / "empirical_pwin.json").write_text("{ bozuk json", encoding="utf-8")
    assert ep.lookup("4h", "NEUTRAL") is None  # bozuk → crash yok


def test_write_table_roundtrip_and_cache_refresh(ep_env, monkeypatch) -> None:
    from packages.learning import outcomes as outcomes_mod
    monkeypatch.setattr(
        outcomes_mod, "outcomes_from_state",
        lambda state=None: [_o("4h", "NEUTRAL", +1) for _ in range(6)]
        + [_o("4h", "NEUTRAL", -1) for _ in range(4)],
    )
    with threshold_override(_OFF_MIN5):
        t = ep.write_table()
        assert t["sufficient_count"] == 1
        hit = ep.lookup("4h", "NEUTRAL")
        assert hit is not None and hit.p_win == pytest.approx(0.6)
        # yeniden yazım cache'i tazeler
        monkeypatch.setattr(
            outcomes_mod, "outcomes_from_state",
            lambda state=None: [_o("4h", "NEUTRAL", +1) for _ in range(10)],
        )
        ep.write_table()
        assert ep.lookup("4h", "NEUTRAL").p_win == 1.0


# ----------------------------- karar motoru ----------------------------------

def _decide(monkeypatch):
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision import engine as dec
    from packages.regime.classifier import classify
    from packages.risk.engine import RiskDecision

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    fake = ConsensusResult(
        symbol="BTCUSD", score=65.0, direction="bullish", confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=65.0, weight=1.0, contribution=65.0)],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)
    hold = RiskDecision(action="HOLD", reason="ok", evidence=[])
    return dec.decide_for_symbol("BTCUSD", snap, regime, hold, timeframe="4h"), regime


def test_engine_flag_off_observes_only(ep_env, monkeypatch) -> None:
    from packages.decision import engine as dec

    # her (tf, rejim) için ampirik p=0.65 döndür (kaynağı izole test etmek için)
    monkeypatch.setattr(
        dec.empirical_pwin, "lookup",
        lambda tf, rg: ep.EmpiricalPwin(p_win=0.65, wins=13, losses=7, n=20, source="tf_regime"),
    )
    d, _ = _decide(monkeypatch)
    assert d.action == "open_long"
    # skor 65 → raw 0.30; identity kalibrasyon → cal_conf 0.30; RR(4h)=2.0, cost 0.1
    assert d.expected_value == pytest.approx(dec._expected_value(0.30, 2.0, 0.1), abs=1e-3)
    # ampirik değerler SALT-GÖZLEM olarak damgalı
    assert d.p_win_empirical == pytest.approx(0.65)
    assert d.expected_value_empirical == pytest.approx(
        dec._expected_value(0.65, 2.0, 0.1), abs=1e-3
    )


def test_engine_flag_on_uses_empirical_p(ep_env, monkeypatch) -> None:
    from packages.decision import engine as dec

    monkeypatch.setattr(
        dec.empirical_pwin, "lookup",
        lambda tf, rg: ep.EmpiricalPwin(p_win=0.65, wins=13, losses=7, n=20, source="tf_regime"),
    )
    with threshold_override(_ON):
        d, _ = _decide(monkeypatch)
    assert d.expected_value == pytest.approx(dec._expected_value(0.65, 2.0, 0.1), abs=1e-3)


def test_engine_flag_on_falls_back_without_evidence(ep_env, monkeypatch) -> None:
    from packages.decision import engine as dec

    monkeypatch.setattr(dec.empirical_pwin, "lookup", lambda tf, rg: None)
    with threshold_override(_ON):
        d, _ = _decide(monkeypatch)
    # kanıt yok → cal_conf tabanlı EV (sahte p uydurulmaz), gözlem alanları None
    assert d.expected_value == pytest.approx(dec._expected_value(0.30, 2.0, 0.1), abs=1e-3)
    assert d.p_win_empirical is None
    assert d.expected_value_empirical is None


# --------------------- F5-3: ödül-ağırlıklı EV kapısı ------------------------
# NOT: conftest autouse fixture'ı `_ev_gate_cfg`'yi {"enabled": False}'a sabitler
# (F5 canlı ama çoğu test pre-F5 davranışını varsayar). Bu yüzden EV kapısını
# doğrulayan testler mevcut F5 deseni gibi `_ev_gate_cfg`'yi DOĞRUDAN monkeypatch
# eder (threshold_override EV config'ini bu pin yüzünden göremez).

_EMP_CELL = dict(p_win=0.58, wins=29, losses=21, n=50, source="tf_regime",
                 avg_win_r=0.6, avg_loss_r=1.2, win_r_n=29, loss_r_n=21)


def _ev_on(monkeypatch, *, payoff_weighted: bool, cell: dict | None = _EMP_CELL) -> None:
    from packages.decision import engine as dec
    monkeypatch.setattr(
        dec, "_ev_gate_cfg",
        lambda: {"enabled": True, "min_ev": 0.0, "cost_r": 0.1,
                 "payoff_weighted": payoff_weighted},
    )
    monkeypatch.setattr(dec.empirical_pwin, "enabled", lambda: True)  # p kaynağı = empirical
    monkeypatch.setattr(
        dec.empirical_pwin, "lookup",
        lambda tf, rg: ep.EmpiricalPwin(**cell) if cell else None,
    )


def test_payoff_weighted_blocks_when_realized_payoff_negative(ep_env, monkeypatch) -> None:
    # p=0.58 ama gerçekleşen kazanç küçük (+0.6R), kayıp büyük (−1.2R):
    # EV = 0.58×0.6 − 0.42×1.2 − 0.1 = 0.348 − 0.504 − 0.1 = −0.256 < 0 → blok.
    _ev_on(monkeypatch, payoff_weighted=True)
    d, _ = _decide(monkeypatch)
    assert d.action == "hold"
    assert "ev_gate" in d.blocked_by
    assert d.expected_value == pytest.approx(0.58 * 0.6 - 0.42 * 1.2 - 0.1, abs=1e-3)


def test_fixed_rr_would_have_allowed_same_trade(ep_env, monkeypatch) -> None:
    # AYNI hücre sabit-RR ile: EV = 0.58×2.0 − 0.42×1 − 0.1 = 0.64 > 0 → açılırdı.
    # Ödül-ağırlıklının asıl değeri: sabit-RR'nin gizlediği negatif edge'i yakalar.
    _ev_on(monkeypatch, payoff_weighted=False)
    d, _ = _decide(monkeypatch)
    assert d.action == "open_long"  # sabit-RR EV pozitif → geçer (eski davranış)


def test_payoff_weighted_falls_back_without_r_data(ep_env, monkeypatch) -> None:
    # Flag ON ama hücrede R verisi yok → dürüstçe sabit-RR formülüne düşer.
    from packages.decision import engine as dec

    _ev_on(monkeypatch, payoff_weighted=True,
           cell=dict(p_win=0.65, wins=13, losses=7, n=20, source="tf_regime",
                     avg_win_r=None, avg_loss_r=None))
    d, _ = _decide(monkeypatch)
    # R yok → sabit-RR formülü, empirical p (0.65) ile — payoff devreye girmez
    assert d.expected_value == pytest.approx(dec._expected_value(0.65, 2.0, 0.1), abs=1e-3)
