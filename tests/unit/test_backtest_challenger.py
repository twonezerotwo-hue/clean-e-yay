"""B-2 (2026-07-05) — rejim-çeşitli outcome üretimi (izole challenger kanalı).

Pinlenen sözleşme:
- LOOK-AHEAD YOK: index k'daki KARAR, seri k'da kesilince ile tam seride BİREBİR
  aynı (gelecek bar karara sızmaz); outcome AYRI (gelecekteki bar) — yalnız LABEL.
- İZOLASYON: produce_outcomes yalnız challenger artifact'larına yazar; canlı
  outcome defterine/ağırlığa/paper state'e ASLA dokunmaz.
- Determinizm: aynı geçmiş aynı jsonl'i üretir (overwrite; çift kayıt yok).
- news geçmişe kurulamaz → her kayıt + meta news_reconstructed=False.
- Son `horizon` indeks atlanır (ufuk verisi yok → outcome uydurulmaz).
- FRED anahtarı yoksa graceful: fred_liquidity=False, çökme yok.
- Flag OFF → worker adımı no-op (fidelity flag'inden AYRI kapı).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.providers.rotation.engine import ROTATION_SYMBOLS
from packages.data.types import OHLCVBar
from packages.learning import backtest_recon as br


def _series(symbol, n, start_close=100.0, drift=0.5, start_day=1):
    base = datetime(2025, 1, start_day, tzinfo=UTC)
    return [
        OHLCVBar(
            symbol=symbol, timeframe="1d", ts=base + timedelta(days=i),
            open=start_close + i * drift, high=start_close + i * drift + 1,
            low=start_close + i * drift - 1, close=start_close + i * drift,
            volume=1000.0, source="test", verified=True,
        )
        for i in range(n)
    ]


def _full_bars(n=80):
    syms = set(ROTATION_SYMBOLS.values()) | {"BTCUSD"}
    return {s: _series(s, n, start_close=100.0 + hash(s) % 20, drift=0.5) for s in syms}


def _macro(n=80):
    # US10Y/US02Y/CPI OHLCV'de yok (FRED) — bilerek boş; Likidite düşer.
    return {"DXY": _series("DXY", n, 100.0, 0.1), "VIX": _series("VIX", n, 15.0, 0.05)}


def _redirect(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKTEST_CHALLENGER_PATH", str(tmp_path / "chal.jsonl"))
    monkeypatch.setenv("BACKTEST_CHALLENGER_META_PATH", str(tmp_path / "chal.json"))


# ---------------------------------------------------------------- flag / gate

def test_challenger_flag_default_off():
    assert br.challenger_enabled() is False


def test_worker_step_gated_by_flag(monkeypatch):
    """Worker adımı `challenger_enabled()` kapısıyla sürülür — flag OFF iken
    run_if_due ÇAĞRILMAZ. run_once koşturmadan gate'i pinler (B-1'deki in-process
    modül-cache sızıntısı dersi: unit testte tam worker koşturma)."""
    called = {"n": 0}
    monkeypatch.setattr(br, "run_if_due", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    monkeypatch.delenv("BACKTEST_CHALLENGER_ENABLED", raising=False)
    if br.challenger_enabled():
        br.run_if_due()
    assert called["n"] == 0
    monkeypatch.setenv("BACKTEST_CHALLENGER_ENABLED", "1")
    if br.challenger_enabled():
        br.run_if_due()
    assert called["n"] == 1


# ---------------------------------------------------------------- üretim

def test_produce_outcomes_isolated(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    out = br.produce_outcomes(bars_by_symbol=_full_bars(), macro_by_symbol=_macro(), horizon=5)
    assert out["status"] == "OK"
    assert out["records"] > 0
    # Yalnız izole challenger artifact'ları yazıldı (canlı deftere DEĞİL).
    assert (tmp_path / "chal.jsonl").exists()
    assert (tmp_path / "chal.json").exists()
    recs = br.read_challenger()
    assert len(recs) == out["records"]


def test_no_lookahead_decision_invariant_to_future(monkeypatch, tmp_path):
    """Kesin look-ahead kanıtı: index k'daki KARAR, seriyi k'da kesince ile tam
    seride birebir aynı olmalı (gelecek bar karara girmez)."""
    k = 60
    full_bars, full_macro = _full_bars(80), _macro(80)
    trunc_bars = {s: v[: k + 1] for s, v in full_bars.items()}
    trunc_macro = {s: v[: k + 1] for s, v in full_macro.items()}
    d_full = br.reconstruct_decision_at(full_bars, full_macro, k)
    d_trunc = br.reconstruct_decision_at(trunc_bars, trunc_macro, k)
    assert d_full.error is None and d_trunc.error is None
    assert d_full.direction == d_trunc.direction
    assert d_full.combined_score == d_trunc.combined_score
    assert d_full.dominant_module == d_trunc.dominant_module
    assert d_full.module_contributions == d_trunc.module_contributions


def test_horizon_boundary_excludes_last(monkeypatch, tmp_path):
    """Son `horizon` indeks kayıt üretmez (ufuk verisi yok → outcome uydurulmaz)."""
    _redirect(monkeypatch, tmp_path)
    n, horizon = 80, 5
    br.produce_outcomes(bars_by_symbol=_full_bars(n), macro_by_symbol=_macro(n), horizon=horizon)
    recs = br.read_challenger()
    max_index = max(r["index"] for r in recs)
    assert max_index <= n - horizon - 1
    # Her kayıt tam bir outcome taşır (ufuk-içi).
    assert all(r["forward_return"] is not None for r in recs)
    assert all(r["horizon_bars"] == horizon for r in recs)


def test_produce_outcomes_deterministic(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    bars, macro = _full_bars(), _macro()
    br.produce_outcomes(bars_by_symbol=bars, macro_by_symbol=macro, horizon=5)
    first = (tmp_path / "chal.jsonl").read_text(encoding="utf-8")
    br.produce_outcomes(bars_by_symbol=bars, macro_by_symbol=macro, horizon=5)
    second = (tmp_path / "chal.jsonl").read_text(encoding="utf-8")
    assert first == second  # overwrite, çift kayıt yok


# ---------------------------------------------------------------- outcome matematiği

def test_fill_outcome_math():
    """forward_return = (exit−entry)/entry; directional_return yön-işaretli;
    label ölü-bant üstünde WIN/LOSS."""
    closes = [0.0] * 10
    closes[3], closes[8] = 100.0, 110.0  # +%10, horizon 5
    rec = br.DecisionRecord(
        as_of="t3", index=3, symbol="BTCUSD", regime_label="OFFENSIVE",
        direction="bullish", combined_score=60.0, dominant_module="touche",
        module_contributions={},
    )
    br._fill_outcome(rec, closes, 5, "t8")
    assert rec.forward_return == 0.1
    assert rec.directional_return == 0.1
    assert rec.label == "WIN"
    # bearish yön → aynı fiyat artışı LOSS.
    rec2 = br.DecisionRecord(
        as_of="t3", index=3, symbol="BTCUSD", regime_label="DEFENSIVE",
        direction="bearish", combined_score=40.0, dominant_module="touche",
        module_contributions={},
    )
    br._fill_outcome(rec2, closes, 5, "t8")
    assert rec2.directional_return == -0.1
    assert rec2.label == "LOSS"
    # neutral → yön ödülü yok → FLAT.
    rec3 = br.DecisionRecord(
        as_of="t3", index=3, symbol="BTCUSD", regime_label="NEUTRAL",
        direction="neutral", combined_score=50.0, dominant_module="touche",
        module_contributions={},
    )
    br._fill_outcome(rec3, closes, 5, "t8")
    assert rec3.directional_return == 0.0
    assert rec3.label == "FLAT"


def test_fill_outcome_no_future_is_empty():
    """Ufuk verisi yoksa outcome boş kalır (uydurma yok)."""
    closes = [100.0, 101.0, 102.0]
    rec = br.DecisionRecord(
        as_of="t2", index=2, symbol="BTCUSD", regime_label="NEUTRAL",
        direction="bullish", combined_score=60.0, dominant_module="touche",
        module_contributions={},
    )
    br._fill_outcome(rec, closes, 5, None)  # index+horizon = 7 ≥ len
    assert rec.forward_return is None
    assert rec.label is None


# ---------------------------------------------------------------- damga / şekil

def test_news_stamped_neutral(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    br.produce_outcomes(bars_by_symbol=_full_bars(), macro_by_symbol=_macro(), horizon=5)
    recs = br.read_challenger()
    assert all(r["news_reconstructed"] is False for r in recs)
    import json
    meta = json.loads((tmp_path / "chal.json").read_text(encoding="utf-8"))
    assert meta["news_reconstructed"] is False


def test_module_contributions_shape():
    # news_abstain CANLI (2026-07-13): geçmişe haber kurulamaz → news normalde
    # düşer; bu test SHAPE kanıtı (news dahil 5 modül) → flag'i explicit kapat.
    from packages.data.registry.loader import threshold_override
    with threshold_override({"consensus": {"news_abstain": False}}):
        d = br.reconstruct_decision_at(_full_bars(), _macro(), 79)
    assert d.error is None
    mc = d.module_contributions
    assert mc is not None
    # news modülü her zaman girer (nötr 50) → shape kanıtı.
    assert "news" in mc
    for _name, cell in mc.items():
        assert set(cell.keys()) == {"score", "weight", "contribution"}


def test_fred_absent_graceful(monkeypatch, tmp_path):
    """FRED anahtarı yok → Likidite düşer ama üretim çökmemeli (damgalı)."""
    _redirect(monkeypatch, tmp_path)
    out = br.produce_outcomes(bars_by_symbol=_full_bars(), macro_by_symbol=_macro(), horizon=5)
    assert out["fred_liquidity"] is False
    assert out["status"] == "OK"


def test_regime_field_present(monkeypatch, tmp_path):
    """Her kayıt rejim etiketi taşır (cat 6/7 rejim-bazlı gruplamanın girdisi)."""
    _redirect(monkeypatch, tmp_path)
    br.produce_outcomes(bars_by_symbol=_full_bars(), macro_by_symbol=_macro(), horizon=5)
    recs = br.read_challenger()
    assert all(r.get("regime_label") for r in recs)


# ---------------------------------------------------------------- interval-gate

def test_run_if_due_interval_gate(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    monkeypatch.setattr(br, "_load_series", lambda: (_full_bars(), _macro()))
    monkeypatch.setenv("BACKTEST_CHALLENGER_INTERVAL_SEC", "86400")
    first = br.run_if_due()
    assert first["status"] == "OK"
    second = br.run_if_due()  # meta taze → interval kapısı
    assert second["status"] == "CACHED"


# ---------------------------------------------------------------- FRED get_history

def test_fred_get_history_no_key_returns_empty(monkeypatch):
    from packages.data.providers.price import fred
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert fred.get_history("US10Y") == []
    assert fred.get_history("UNKNOWN") == []
