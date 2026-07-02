"""F2-1 — mark-to-market SALT-GÖZLEM testleri.

- PaperState.unrealized_pnl_usd / mtm_equity_usd türetilir (persist edilmez).
- Değerleme tek kaynaktan (execution_sim.unrealized_pnl) gelir.
- heartbeat.record MTM alanlarını taşır; verilmezse None (FAILED/legacy güvenli).
- system_health worker view MTM alanlarını geçirir; UNKNOWN/legacy → None.
- RiskGate davranışı DEĞİŞMEZ: MTM hiçbir gate girdisine bağlanmadı (gözlem).
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from packages.paper import execution_sim
from packages.paper.state import PaperState, Position


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_HEARTBEAT_PATH", str(tmp_path / "heartbeats.json"))
    return tmp_path


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _pos(symbol: str, side: str, entry: float, current: float, size: float) -> Position:
    return Position(
        id=f"p-{symbol}-{side}", symbol=symbol, side=side,
        entry_price=entry, current_price=current, size_usd=size,
        sl=None, tp=None, opened_at=_utc_iso(),
    )


# ------------------------------ PaperState MTM --------------------------------

def test_mtm_empty_state_equals_realized_equity() -> None:
    ps = PaperState(equity_usd=10_000.0, peak_equity_usd=10_000.0)
    assert ps.unrealized_pnl_usd == 0.0
    assert ps.mtm_equity_usd == 10_000.0


def test_mtm_sums_open_positions_long_and_short() -> None:
    ps = PaperState(
        equity_usd=10_000.0,
        peak_equity_usd=10_000.0,
        open_positions=[
            _pos("BTC", "long", entry=100.0, current=110.0, size=1_000.0),
            _pos("ETH", "short", entry=50.0, current=55.0, size=500.0),
        ],
    )
    expected = execution_sim.unrealized_pnl("long", 100.0, 110.0, 1_000.0) + \
        execution_sim.unrealized_pnl("short", 50.0, 55.0, 500.0)
    assert ps.unrealized_pnl_usd == pytest.approx(expected)
    assert ps.mtm_equity_usd == pytest.approx(10_000.0 + expected)
    # Yön işaretleri: long lehte (+), short aleyhte (−) — toplam net.
    assert execution_sim.unrealized_pnl("long", 100.0, 110.0, 1_000.0) > 0
    assert execution_sim.unrealized_pnl("short", 50.0, 55.0, 500.0) < 0


def test_mtm_is_derived_not_persisted() -> None:
    """Salt-gözlem: state şeması değişmez — MTM diske yazılmaz, her okuyuşta
    güncel current_price'tan türetilir (bayat MTM persist edilemez)."""
    ps = PaperState(
        equity_usd=10_000.0, peak_equity_usd=10_000.0,
        open_positions=[_pos("BTC", "long", 100.0, 110.0, 1_000.0)],
    )
    d = ps.to_dict()
    assert "unrealized_pnl_usd" not in d
    assert "mtm_equity_usd" not in d
    # Roundtrip sonrası türetim aynı kalır (schema_version değişmedi).
    assert PaperState.from_dict(d).mtm_equity_usd == pytest.approx(ps.mtm_equity_usd)


# ------------------------------ heartbeat MTM ---------------------------------

def test_heartbeat_carries_mtm_observation(ops_env) -> None:
    from packages.ops import heartbeat
    heartbeat.record(
        "tick_worker", status="OK", run_id="r1", started_at=_utc_iso(),
        completed_at=_utc_iso(), unrealized_pnl_usd=12.34, mtm_equity_usd=10_012.34,
    )
    hb = heartbeat.load("tick_worker")
    assert hb["unrealized_pnl_usd"] == pytest.approx(12.34)
    assert hb["mtm_equity_usd"] == pytest.approx(10_012.34)


def test_heartbeat_mtm_defaults_none(ops_env) -> None:
    """FAILED cycle / learning_worker MTM geçmez → None (0.0 uydurulmaz)."""
    from packages.ops import heartbeat
    heartbeat.record("learning_worker", status="NO_DATA", run_id="r1", started_at=_utc_iso())
    hb = heartbeat.load("learning_worker")
    assert hb["unrealized_pnl_usd"] is None
    assert hb["mtm_equity_usd"] is None


# ----------------------------- system_health MTM ------------------------------

def test_worker_view_passes_mtm_through(ops_env) -> None:
    from packages.ops import heartbeat, system_health
    heartbeat.record(
        "tick_worker", status="OK", run_id="r1", started_at=_utc_iso(),
        completed_at=_utc_iso(), unrealized_pnl_usd=-5.5, mtm_equity_usd=9_994.5,
    )
    tick = system_health.build_system_health()["workers"]["tick_worker"]
    assert tick["unrealized_pnl_usd"] == pytest.approx(-5.5)
    assert tick["mtm_equity_usd"] == pytest.approx(9_994.5)


def test_worker_view_mtm_none_for_unknown_and_legacy(ops_env) -> None:
    """Hiç çalışmamış worker + MTM alansız legacy heartbeat → None (crash yok)."""
    import json

    from packages.ops import heartbeat, system_health
    # Legacy heartbeat: MTM alanları dosyada yok.
    legacy = {
        "tick_worker": {
            "worker_name": "tick_worker", "run_id": "old", "status": "OK",
            "started_at": _utc_iso(), "completed_at": _utc_iso(),
        }
    }
    (ops_env / "heartbeats.json").write_text(json.dumps(legacy), encoding="utf-8")
    assert heartbeat.load("tick_worker")["run_id"] == "old"
    sh = system_health.build_system_health()
    assert sh["workers"]["tick_worker"]["unrealized_pnl_usd"] is None
    assert sh["workers"]["tick_worker"]["mtm_equity_usd"] is None
    # learning_worker hiç heartbeat yazmadı → UNKNOWN görünümü de alanları taşır.
    assert sh["workers"]["learning_worker"]["unrealized_pnl_usd"] is None
    assert sh["workers"]["learning_worker"]["mtm_equity_usd"] is None
