"""G5 — Daily-loss / Max-DD halt testleri.

- Daily loss breach → DAILY_LOSS halt aktif (KILL_SWITCH seviyesi).
- Max DD breach → MAX_DRAWDOWN halt aktif (RISK_REDUCE seviyesi).
- Halt aktif → risk engine escalate eder, yeni paper pozisyon açılmaz.
- KILL_SWITCH halt → flatten_all (KILL_SWITCH_EXIT) — paper-safe; fiyatı
  olmayan pozisyon kapatılmaz (mock fiyat yok).
- **Otomatik reset yok**: breach geçse / gün dönse de halt aktif kalır;
  yalnızca owner reset endpoint'i kapatır.
- DQS BLOCKED → trade yok (halt'ten bağımsız). Hepsi offline.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("REBALANCE_STORE_PATH", str(tmp_path / "rebalance.json"))
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(tmp_path / "weights_active.json"))
    monkeypatch.setenv("WEIGHTS_OUTPUT_DIR", str(tmp_path / "weights_out"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def _risk_input(
    *,
    equity: float = 100_000,
    peak: float = 100_000,
    daily_pnl: float = 0.0,
    dqs: float = 100.0,
    open_count: int = 0,
):
    from packages.risk.engine import RiskInput
    return RiskInput(
        dqs_score=dqs,
        equity_usd=equity,
        peak_equity_usd=peak,
        daily_pnl_usd=daily_pnl,
        open_position_count=open_count,
    )


def _position(
    ps, *, symbol: str = "BTCUSD", side: str = "long", size_usd: float = 10_000,
    price: float = 100.0,
):
    return ps.Position(
        id=f"{symbol}-{side}",
        symbol=symbol,
        side=side,
        entry_price=price,
        current_price=price,
        size_usd=size_usd,
        sl=None,
        tp=None,
        opened_at="2026-06-11T00:00:00+00:00",
    )


# ---------------- halt store ----------------

def test_daily_loss_breach_activates_halt(fresh_env) -> None:
    from packages.risk import halt
    # %2 limit: 100k equity → -2000; -2500 breach
    active = halt.sync(_risk_input(daily_pnl=-2500))
    assert len(active) == 1
    assert active[0].type == "DAILY_LOSS"
    assert active[0].level == "KILL_SWITCH"
    # Persist edildi
    assert halt.active_halts()[0].type == "DAILY_LOSS"


def test_max_dd_breach_activates_halt(fresh_env) -> None:
    from packages.risk import halt
    # %8 DD limiti: peak 100k, equity 91k → %9 breach
    active = halt.sync(_risk_input(equity=91_000, peak=100_000))
    assert len(active) == 1
    assert active[0].type == "MAX_DRAWDOWN"
    assert active[0].level == "RISK_REDUCE"


def test_halt_is_idempotent_and_sticky(fresh_env) -> None:
    from packages.risk import halt
    halt.sync(_risk_input(daily_pnl=-2500))
    halt.sync(_risk_input(daily_pnl=-2500))  # aynı tip tekrar açılmaz
    assert len(halt.load().events) == 1
    # Otomatik reset yok: breach geçse de (gün dönümü vb.) halt aktif kalır
    active = halt.sync(_risk_input(daily_pnl=0.0))
    assert len(active) == 1
    assert active[0].active is True


def test_owner_reset_clears_halts(fresh_env) -> None:
    from packages.risk import halt
    halt.sync(_risk_input(daily_pnl=-2500, equity=91_000, peak=100_000))
    assert len(halt.active_halts()) == 2
    cleared = halt.owner_reset()
    assert len(cleared) == 2
    assert halt.active_halts() == []
    # Geçmiş korunur
    assert all(e.cleared_by == "owner_reset" for e in halt.load().events)


# ---------------- risk engine entegrasyonu ----------------

def test_engine_escalates_on_active_daily_halt(fresh_env) -> None:
    from packages.risk import halt
    from packages.risk.engine import evaluate
    halt.sync(_risk_input(daily_pnl=-2500))
    # Breach geçti ama halt sticky → KILL_SWITCH sürer
    d = evaluate(_risk_input(daily_pnl=0.0))
    assert d.action == "KILL_SWITCH"
    assert "halt" in d.reason


def test_engine_escalates_on_active_dd_halt(fresh_env) -> None:
    from packages.risk import halt
    from packages.risk.engine import evaluate
    halt.sync(_risk_input(equity=91_000, peak=100_000))
    d = evaluate(_risk_input(equity=100_000, peak=100_000))
    assert d.action == "RISK_REDUCE"


def test_engine_unchanged_without_halt(fresh_env) -> None:
    from packages.risk.engine import evaluate
    d = evaluate(_risk_input())
    assert d.action == "HOLD"


def test_dqs_blocked_beats_everything(fresh_env) -> None:
    """DQS düşük → KILL_SWITCH; halt olsun olmasın trade yok."""
    from packages.risk.engine import evaluate
    d = evaluate(_risk_input(dqs=40.0))
    assert d.action == "KILL_SWITCH"


# ---------------- paper-safe davranış ----------------

def test_flatten_all_closes_positions_with_price(fresh_env) -> None:
    from packages.paper.lifecycle import flatten_all
    ps = fresh_env
    state = ps.load()
    state.open_positions.append(_position(ps, symbol="BTCUSD"))
    state.open_positions.append(_position(ps, symbol="ETHUSD"))
    closed = flatten_all(state, {"BTCUSD": 105.0})  # ETH fiyatı yok
    assert len(closed) == 1
    assert closed[0].close_reason == "KILL_SWITCH_EXIT"
    # Fiyatı olmayan pozisyon açık kalır (mock fiyat uydurulmaz)
    assert [p.symbol for p in state.open_positions] == ["ETHUSD"]


def test_halt_active_no_new_positions_via_tick(fresh_env) -> None:
    """Daily-loss breach'li state → tick: halt aktive olur, open yok,
    mevcut pozisyon KILL_SWITCH_EXIT ile kapanır."""
    ps = fresh_env
    state = ps.load()
    state.daily_pnl_usd = -5000.0  # %2 limitin çok üstünde
    state.daily_anchor_date = "2099-12-31"  # tick'te gün sıfırlamasın
    # entry/current fiyat mock provider'ın BTCUSD taban fiyatıyla (68000,
    # packages/data/providers/price/mock.py) UYUMLU olmalı — testler
    # TEST_USE_MOCK=true ile çalışır (bkz. kök conftest.py) ve price_sanity
    # guard'ı gerçek/mock fiyata göre >%30 "imkansız sıçrama" gördüğünde
    # current_price'ı GÜNCELLEMEZ (DATA_POLICY) — pozisyon sonsuza dek
    # EXIT_PENDING'de kalır, flatten_all hiç gerçekleşmez. 100.0 sentetik
    # fiyatı bu yüzden testi kilitliyordu.
    state.open_positions.append(_position(ps, symbol="BTCUSD", price=68_000.0))
    ps.save(state)

    # T1 — tek tick yolu worker (POST /paper-trading/tick kaldırıldı).
    import asyncio

    from apps.tick_worker import main as tick_worker
    from packages.ops import heartbeat

    asyncio.run(tick_worker.run_once())
    assert heartbeat.load("tick_worker")["status"] != "FAILED"

    from packages.risk import halt
    assert any(h.type == "DAILY_LOSS" for h in halt.active_halts())
    after = ps.load()
    assert after.open_positions == []  # flatten — halt aktifken open da yok
    assert any(
        t.close_reason == "KILL_SWITCH_EXIT" for t in after.recent_trades
    )


def test_dd_halt_blocks_new_positions_keeps_existing(fresh_env) -> None:
    """Max-DD halt (RISK_REDUCE) → yeni açılış yok; flatten da yok."""
    ps = fresh_env
    state = ps.load()
    state.equity_usd = 90_000.0
    state.peak_equity_usd = 100_000.0  # DD %10 ≥ %8
    state.open_positions.append(_position(ps, symbol="BTCUSD"))
    ps.save(state)

    # T1 — tek tick yolu worker (POST /paper-trading/tick kaldırıldı).
    import asyncio

    from apps.tick_worker import main as tick_worker
    from packages.ops import heartbeat

    asyncio.run(tick_worker.run_once())
    assert heartbeat.load("tick_worker")["status"] != "FAILED"

    after = ps.load()
    # RISK_REDUCE: yeni açılış yok (mevcut 1 pozisyon dışında) ve flatten yok
    assert len(after.open_positions) == 1
    assert any(
        t.close_reason == "KILL_SWITCH_EXIT" for t in after.recent_trades
    ) is False


# ---------------- endpoints ----------------

def test_halts_endpoint_and_owner_reset(fresh_env) -> None:
    from packages.risk import halt
    halt.sync(_risk_input(daily_pnl=-2500))

    from apps.api.main import app
    client = TestClient(app)

    r = client.get("/api/v1/risk/halts")
    assert r.status_code == 200
    body = r.json()
    assert body["halt_active"] is True
    assert body["active"][0]["type"] == "DAILY_LOSS"
    assert "daily_loss_ratio" in body["metrics"]
    assert "drawdown_ratio" in body["metrics"]

    r2 = client.post("/api/v1/risk/halts/reset")
    assert r2.status_code == 200
    assert r2.json()["cleared_count"] == 1

    r3 = client.get("/api/v1/risk/halts")
    assert r3.json()["halt_active"] is False
    # Timeline'da geçmiş event durur
    assert r3.json()["timeline"][0]["cleared_by"] == "owner_reset"


def test_halts_metrics_ratios(fresh_env) -> None:
    from packages.risk import halt
    m = halt.metrics(_risk_input(equity=96_000, peak=100_000, daily_pnl=-960))
    # daily limit = %2 × 96k = 1920; loss 960 → ratio 0.5
    assert m["daily_loss_ratio"] == pytest.approx(0.5)
    # DD = 4% / 8% → ratio 0.5
    assert m["drawdown_ratio"] == pytest.approx(0.5)
