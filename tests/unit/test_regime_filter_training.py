"""F3-2 — rejim-filtreli ağırlık eğitimi testleri.

- Flag KAPALI (default): tüm rejimlerin outcome'ları tek torbada — eski
  davranış birebir (dataset_size hepsini sayar).
- Flag AÇIK: dataset hedef rejimin KENDİ outcome'larına daralır; az verili
  rejim MIN_TOTAL_TRADES frenine takılır (INSUFFICIENT, rejim etiketli).
- Bilinmeyen rejim etiketi weights'e sahte satır açamaz (NEUTRAL'a düşer).
- `latest_outcome_regime`: en son kapanan verified outcome'un rejimi.
"""
from __future__ import annotations

import importlib


def _fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper_state.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    monkeypatch.setenv("REBALANCE_STORE_PATH", str(tmp_path / "rebalance.json"))
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(tmp_path / "weights_active.json"))
    monkeypatch.setenv("WEIGHTS_OUTPUT_DIR", str(tmp_path / "weights_out"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def _seed(ps, *, regime: str, module: str, n: int, wins: int,
          id_prefix: str, closed_at: str = "2026-06-11T01:00:00+00:00") -> None:
    state = ps.load()
    for i in range(n):
        state.recent_trades.append(
            ps.Trade(
                id=f"{id_prefix}{i}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=101.0,
                pnl_usd=120.0 if i < wins else -50.0,
                opened_at="2026-06-11T00:00:00+00:00",
                closed_at=closed_at,
                close_reason="TP_HIT",
                fingerprint=f"BTCUSD|{regime}|bullish|S65|C|{module}",
                data_verified=True,
            )
        )
    ps.save(state)


def _seed_two_regimes(ps) -> None:
    # NEUTRAL: 12 işlem (touche 6W + fundamental 0W) → tek başına eğitime yeter
    _seed(ps, regime="NEUTRAL", module="touche", n=6, wins=6, id_prefix="nt")
    _seed(ps, regime="NEUTRAL", module="fundamental", n=6, wins=0, id_prefix="nf")
    # CRISIS: yalnız 4 işlem → tek başına MIN_TOTAL_TRADES (10) altı
    _seed(ps, regime="CRISIS", module="touche", n=2, wins=2, id_prefix="ct",
          closed_at="2026-06-12T01:00:00+00:00")
    _seed(ps, regime="CRISIS", module="fundamental", n=2, wins=0, id_prefix="cf",
          closed_at="2026-06-12T01:00:00+00:00")


def test_flag_off_all_regimes_in_one_bag(tmp_path, monkeypatch) -> None:
    ps = _fresh_env(tmp_path, monkeypatch)
    monkeypatch.delenv("WEIGHT_REGIME_FILTER", raising=False)
    _seed_two_regimes(ps)
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="NEUTRAL")
    assert hasattr(res, "deltas")
    assert res.dataset_size == 16  # 12 NEUTRAL + 4 CRISIS — eski davranış birebir


def test_flag_on_dataset_narrows_to_target_regime(tmp_path, monkeypatch) -> None:
    ps = _fresh_env(tmp_path, monkeypatch)
    monkeypatch.setenv("WEIGHT_REGIME_FILTER", "1")
    _seed_two_regimes(ps)
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="NEUTRAL")
    assert hasattr(res, "deltas")
    assert res.dataset_size == 12  # CRISIS işlemleri torbaya girmedi
    assert res.proposed_yaml["audit"]["regime_filtered"] is True


def test_flag_on_sparse_regime_hits_min_total_brake(tmp_path, monkeypatch) -> None:
    """Az verili rejim eğitilMEZ — minimum-örnek eşiği rejim başına fren."""
    ps = _fresh_env(tmp_path, monkeypatch)
    monkeypatch.setenv("WEIGHT_REGIME_FILTER", "1")
    _seed_two_regimes(ps)
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="CRISIS")
    assert isinstance(res, dict)
    assert res["status"] == "INSUFFICIENT"
    assert res["reason"] == "below_min_total"
    assert res["dataset_size"] == 4
    assert res["regime"] == "CRISIS"
    assert res["regime_filtered"] is True


def test_flag_on_unknown_regime_falls_back_to_neutral(tmp_path, monkeypatch) -> None:
    """Bozuk rejim etiketi weights dosyasına sahte satır açamaz."""
    ps = _fresh_env(tmp_path, monkeypatch)
    monkeypatch.setenv("WEIGHT_REGIME_FILTER", "1")
    _seed_two_regimes(ps)
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="GARBAGE")
    assert hasattr(res, "deltas")
    assert res.regime == "NEUTRAL"
    assert set(res.proposed_yaml["regimes"].keys()) == {
        "OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"
    }


def test_latest_outcome_regime_picks_most_recent(tmp_path, monkeypatch) -> None:
    ps = _fresh_env(tmp_path, monkeypatch)
    _seed_two_regimes(ps)  # CRISIS işlemleri 06-12'de kapandı (daha yeni)
    from packages.learning import auto_weight_trainer as t
    assert t.latest_outcome_regime() == "CRISIS"


def test_latest_outcome_regime_empty_state(tmp_path, monkeypatch) -> None:
    _fresh_env(tmp_path, monkeypatch)
    from packages.learning import auto_weight_trainer as t
    assert t.latest_outcome_regime() is None
