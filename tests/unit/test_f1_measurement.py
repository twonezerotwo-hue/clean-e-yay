"""F1 — ölçüm standardı slice testleri (bkz. docs/AUDIT_ROADMAP.md).

F1-1: R-multiple (risk_pct → r_multiple; EXPECTANCY_R_MODE flag'i default OFF)
F1-2: başabaş (pnl==0) kayıp değildir — bucketize + mistake_memory
F1-3: modül katkı vektörü decision_log'a yazılır + module_attribution okur
F1-4: gün çapası UTC
F1-5: kısmi kapanışta trade id benzersiz (tam kapanış pos.id'yi korur)
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps, tmp_path


def _mk_trade(ps, tid: str, pnl: float, **kw):
    defaults = dict(
        id=tid, symbol="BTCUSD", side="long",
        entry_price=100.0, exit_price=100.0 + pnl / 10.0, pnl_usd=pnl,
        opened_at="2026-07-01T00:00:00+00:00",
        closed_at="2026-07-01T01:00:00+00:00",
        close_reason="TP_HIT" if pnl > 0 else ("SL_HIT" if pnl < 0 else "TIME_STOP_EXIT"),
        fingerprint="BTCUSD|v2|1d|NEUTRAL|bullish|S55|C|touche",
        data_verified=True,
    )
    defaults.update(kw)
    return ps.Trade(**defaults)


# ------------------------------ F1-1: R-multiple ------------------------------

def test_r_multiple_from_risk_pct(env) -> None:
    ps, _ = env
    from packages.learning import outcomes as om
    # entry 100 → exit 106 (long +6%), açılış riski %3 → r = +2.0
    t = _mk_trade(ps, "r1", 60.0, exit_price=106.0, open_risk_pct=0.03)
    o = om.build_outcome(t)
    assert o.risk_pct == 0.03
    assert o.r_multiple == pytest.approx(2.0)


def test_r_multiple_none_without_risk_pct(env) -> None:
    """Legacy/SL'siz kayıt: R hesaplanamaz → None (uydurma yok)."""
    ps, _ = env
    from packages.learning import outcomes as om
    o = om.build_outcome(_mk_trade(ps, "r2", 60.0, exit_price=106.0))
    assert o.risk_pct is None
    assert o.r_multiple is None


def test_close_position_stamps_risk_pct(env) -> None:
    ps, _ = env
    from packages.paper import lifecycle
    state = ps.PaperState(equity_usd=100_000, peak_equity_usd=100_000)
    pos = lifecycle.open_position(
        state, symbol="BTCUSD", side="long", entry_price=100.0, size_multiplier=1.0,
    )
    trade = lifecycle.close_position(state, pos, exit_price=105.0, reason="TP_HIT")
    # SL açılışta konur → risk_pct = |entry−SL|/entry damgalanmış olmalı.
    assert trade.open_risk_pct is not None
    assert trade.open_risk_pct == pytest.approx(abs(100.0 - pos.sl) / 100.0, rel=1e-4)


def test_expectancy_r_mode_flag(env, monkeypatch) -> None:
    """Flag OFF → USD ortalaması (bayt-aynı); ON → yalnız r_multiple örnekleri."""
    ps, _ = env
    state = ps.load()
    # USD büyük ama R küçük bir trade + USD küçük ama R büyük bir trade.
    state.recent_trades.append(
        _mk_trade(ps, "e1", 500.0, exit_price=101.0, open_risk_pct=0.02)   # r=+0.5
    )
    state.recent_trades.append(
        _mk_trade(ps, "e2", 10.0, exit_price=106.0, open_risk_pct=0.02)    # r=+3.0
    )
    state.recent_trades.append(
        _mk_trade(ps, "e3", -100.0, exit_price=99.0)                        # R'siz (legacy)
    )
    ps.save(state)
    from packages.learning import weight_rollback as wr
    monkeypatch.delenv("EXPECTANCY_R_MODE", raising=False)
    n_usd, exp_usd = wr.pre_apply_expectancy(window=10)
    assert n_usd == 3
    assert exp_usd == pytest.approx((500.0 + 10.0 - 100.0) / 3, abs=0.01)
    monkeypatch.setenv("EXPECTANCY_R_MODE", "1")
    n_r, exp_r = wr.pre_apply_expectancy(window=10)
    assert n_r == 2  # R'siz legacy örnek dışı (dürüst daralma)
    assert exp_r == pytest.approx((0.5 + 3.0) / 2, abs=0.01)


# --------------------------- F1-2: başabaş ayrımı ----------------------------

def test_bucketize_breakeven_not_loss(env) -> None:
    ps, _ = env
    from packages.learning import outcomes as om
    outs = [
        om.build_outcome(_mk_trade(ps, "b1", 50.0)),
        om.build_outcome(_mk_trade(ps, "b2", 0.0, exit_price=100.0)),
        om.build_outcome(_mk_trade(ps, "b3", -50.0)),
    ]
    b = om.bucketize(outs, lambda o: o.symbol)["BTCUSD"]
    assert b["trades"] == 3
    assert b["wins"] == 1
    assert b["losses"] == 1
    assert b["breakeven"] == 1
    # win_rate paydası kararlı trade'ler: 1/2, 1/3 DEĞİL.
    assert b["win_rate"] == 0.5


def test_mistake_memory_breakeven_not_loss(env) -> None:
    """3 başabaş trade AVOID tetikleyemez; BE kayıp serisini keser."""
    ps, _ = env
    from packages.learning import mistake_memory as mm
    fp = "BTCUSD|v2|1d|NEUTRAL|bullish|S55|C|touche"
    state = ps.load()
    for i in range(3):
        state.recent_trades.append(
            _mk_trade(ps, f"be{i}", 0.0, exit_price=100.0, fingerprint=fp)
        )
    ps.save(state)
    v = mm.evaluate(fp)
    assert v.action == "NEUTRAL"  # decided=0 < MIN_TRADES — AVOID yok
    # 2 kayıp + 1 BE + 2 kayıp: streak son BE'de kesilir → 2 (< STREAK_AVOID)
    state = ps.load()
    seq = [(-10.0, "s0"), (-10.0, "s1"), (0.0, "s2"), (-10.0, "s3"), (-10.0, "s4")]
    for i, (pnl, tid) in enumerate(seq):
        state.recent_trades.append(
            _mk_trade(
                ps, tid, pnl,
                exit_price=100.0 + pnl / 10.0,
                fingerprint="X|v2|1d|NEUTRAL|bearish|S45|X|touche",
                closed_at=f"2026-07-01T0{i}:00:00+00:00",
            )
        )
    ps.save(state)
    rec = next(
        m for m in mm.summary()
        if m.fingerprint == "X|v2|1d|NEUTRAL|bearish|S45|X|touche"
    )
    assert rec.losses == 4
    assert rec.streak_losses == 2  # BE seriyi kesti


# ------------------------ F1-3: modül katkı vektörü --------------------------

def test_module_contributions_flow_to_decision_log(env) -> None:
    ps, tmp_path = env
    from packages.paper import lifecycle
    state = ps.PaperState(equity_usd=100_000, peak_equity_usd=100_000)
    contrib = {"touche": 24.5, "fundamental": 12.0, "news": 8.2}
    # entry price gerçekçi olmalı — price_sanity mutlak sınır kapısı çalışır.
    pos, _ = lifecycle.attempt_open(
        state, symbol="BTCUSD", side="long", entry_price=60000.0,
        size_multiplier=1.0, module_contributions=contrib,
    )
    assert pos is not None
    assert pos.open_module_contributions == contrib
    trade = lifecycle.close_position(state, pos, exit_price=63000.0, reason="TP_HIT")
    assert trade.open_module_contributions == contrib
    # decision_log kaydı vektörü taşımalı.
    log_path = Path(tmp_path / "decision_log.jsonl")
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["opening_signal"]["module_contributions"] == contrib


def test_module_attribution_report(env) -> None:
    ps, _ = env
    from packages.learning import outcomes as om
    outs = [
        om.build_outcome(_mk_trade(
            ps, "ma1", 50.0,
            open_module_contributions={"touche": 30.0, "news": 5.0},
        )),
        om.build_outcome(_mk_trade(
            ps, "ma2", -50.0,
            open_module_contributions={"touche": 10.0, "news": 15.0},
        )),
        om.build_outcome(_mk_trade(ps, "ma3", 20.0)),  # vektörsüz (legacy) → dışarıda
    ]
    rep = om.module_attribution(outs)
    assert rep["touche"]["win_trades"] == 1
    assert rep["touche"]["loss_trades"] == 1
    assert rep["touche"]["avg_contrib_win"] == 30.0
    assert rep["touche"]["avg_contrib_loss"] == 10.0
    assert rep["news"]["avg_contrib_win"] == 5.0
    assert rep["news"]["avg_contrib_loss"] == 15.0


# ------------------------------ F1-4: UTC çapa --------------------------------

def test_daily_anchor_is_utc(env, monkeypatch) -> None:
    ps, _ = env
    from datetime import UTC, datetime

    from packages.paper import lifecycle
    state = ps.PaperState(equity_usd=100_000, peak_equity_usd=100_000)
    lifecycle._ensure_daily_anchor(state)
    assert state.daily_anchor_date == datetime.now(UTC).date().isoformat()


# --------------------- F1-5: kısmi kapanış id benzersiz -----------------------

def test_partial_close_unique_trade_ids(env) -> None:
    ps, _ = env
    from packages.paper import lifecycle
    state = ps.PaperState(equity_usd=100_000, peak_equity_usd=100_000)
    pos = lifecycle.open_position(
        state, symbol="BTCUSD", side="long", entry_price=100.0, size_multiplier=1.0,
    )
    pos_id = pos.id
    t1 = lifecycle.close_position(
        state, pos, exit_price=105.0, reason="MANUAL", close_size=pos.size_usd / 3
    )
    t2 = lifecycle.close_position(
        state, pos, exit_price=106.0, reason="MANUAL", close_size=pos.size_usd / 2
    )
    # Kısmi leg'ler türetilmiş benzersiz id alır; pozisyon hâlâ açık.
    assert t1.id != pos_id and t2.id != pos_id and t1.id != t2.id
    assert any(p.id == pos_id for p in state.open_positions)
    # Tam kapanış pos.id'yi birebir korur (mevcut davranış).
    t3 = lifecycle.close_position(state, pos, exit_price=107.0, reason="TP_HIT")
    assert t3.id == pos_id
    assert not state.open_positions
