"""P1 — paper lifecycle finalization testleri.

Kapsam (hard kurallar):
- time-stop: fiyat varsa CLOSED/TIME_STOP_EXIT; fiyat yoksa EXPIRED_PENDING_PRICE;
  sonraki tick'te fiyat gelince kapanır; negatif geri sayım yok; fake fiyat yok.
- kill-switch: KILL_SWITCH_EXIT (FORCE_CLOSED); fiyat yoksa EXIT_PENDING.
- duplicate/scale-in: aynı symbol+tf (yön fark etmez) bloklanır; farklı tf serbest;
  scale_in=True explicit'te açılır.
- audit log: open/close/blocked olayları JSONL'e yazılır.
- learning handoff: kapanan Trade gerekli alanları taşır.
- state robustness: corrupt → yedek+default (crash yok); legacy kayıt yüklenir.
- live network bağımlılığı yok (state okuma pipeline çağırmaz).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def paper_env(tmp_path, monkeypatch):
    """İzole paper state + audit + halt yolları (gerçek dosyaya dokunmaz)."""
    from packages.paper import audit
    from packages.paper import state as paper_state

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper_state.json")
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "paper_audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    return {"state": paper_state, "audit": audit, "tmp": tmp_path}


def _past_iso(hours: int = 2) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _open(lifecycle, ps, *, symbol="BTCUSD", side="long", tf="1d",
          entry=100.0, expired=False):
    pos = lifecycle.open_position(
        ps, symbol=symbol, side=side, entry_price=entry, size_multiplier=1.0,
        timeframe=tf, open_reason="unit-test", snapshot_id="snap-1",
        fingerprint="fp-1",
    )
    if expired:
        pos.valid_until = _past_iso()
    return pos


# ---------- time-stop ----------

def test_time_stop_closes_with_price(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps, expired=True)
    closed = lifecycle.tick(ps, {"BTCUSD": 100.5})  # SL/TP'ye değmeyen fiyat
    assert len(closed) == 1
    assert closed[0].close_reason == "TIME_STOP_EXIT"
    assert closed[0].lifecycle_status == "CLOSED"
    assert not ps.open_positions


def test_time_stop_pending_without_price(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps, expired=True)
    closed = lifecycle.tick(ps, {})  # fiyat yok → fake fiyat YOK
    assert closed == []
    p = ps.open_positions[0]
    assert p.lifecycle_status == "EXPIRED_PENDING_PRICE"
    assert p.time_stop_expired is True
    assert p.pending_exit_reason == "TIME_STOP_EXIT"


def test_pending_closes_when_price_arrives(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps, expired=True)
    assert lifecycle.tick(ps, {}) == []                  # önce pending
    closed = lifecycle.tick(ps, {"BTCUSD": 100.5})       # sonra fiyat gelir
    assert len(closed) == 1 and closed[0].close_reason == "TIME_STOP_EXIT"
    assert not ps.open_positions


# ---------- kill-switch / force close ----------

def test_kill_switch_closes_force(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps)
    closed = lifecycle.flatten_all(ps, {"BTCUSD": 100.5})
    assert len(closed) == 1
    assert closed[0].close_reason == "KILL_SWITCH_EXIT"
    assert closed[0].lifecycle_status == "FORCE_CLOSED"


def test_kill_switch_pending_without_price(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps)
    closed = lifecycle.flatten_all(ps, {})  # fiyat yok → açık kalır
    assert closed == []
    p = ps.open_positions[0]
    assert p.lifecycle_status == "EXIT_PENDING"
    assert p.pending_exit_reason == "KILL_SWITCH_EXIT"


def test_risk_reduce_behavior_unchanged_no_force_close(paper_env) -> None:
    """Normal tick (SL/TP/time-stop yok, flatten çağrılmaz) pozisyonu kapatmaz —
    risk-reduce yolu force-close üretmez (davranış değişmedi)."""
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps)  # expired DEĞİL
    closed = lifecycle.tick(ps, {"BTCUSD": 100.5})
    assert closed == []
    assert ps.open_positions[0].lifecycle_status == "OPEN"


# ---------- duplicate / scale-in ----------

def test_duplicate_same_symbol_tf_blocked(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps, symbol="BTCUSD", tf="1d", side="long")
    pos, decision = lifecycle.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=60000.0,
        size_multiplier=1.0, timeframe="1d",
    )
    assert pos is None
    assert decision["allowed"] is False
    assert decision["reason"] == "duplicate_same_tf"
    assert len(ps.open_positions) == 1


def test_opposite_direction_same_tf_blocked_no_hedge(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps, symbol="BTCUSD", tf="1d", side="long")
    pos, decision = lifecycle.attempt_open(
        ps, symbol="BTCUSD", side="short", entry_price=60000.0,
        size_multiplier=1.0, timeframe="1d",
    )
    assert pos is None
    assert decision["reason"] == "opposite_dir_same_tf_no_hedge"


def test_different_timeframe_allowed(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps, symbol="BTCUSD", tf="1d", side="long")
    pos, decision = lifecycle.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=60000.0,
        size_multiplier=1.0, timeframe="4h",
    )
    assert pos is not None and decision["allowed"] is True
    assert len(ps.open_positions) == 2


def test_scale_in_explicit_allowed(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps, symbol="BTCUSD", tf="1d", side="long")
    pos, decision = lifecycle.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=60000.0,
        size_multiplier=1.0, timeframe="1d", scale_in=True,
    )
    assert pos is not None
    assert decision["duplicate"] is True and decision["reason"] == "scale_in"
    assert pos.scale_in is True
    assert len(ps.open_positions) == 2


def test_no_price_blocks_open(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    pos, decision = lifecycle.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=None,
        size_multiplier=1.0, timeframe="1d",
    )
    assert pos is None and decision["reason"] == "no_price"
    assert not ps.open_positions


# ---------- audit log ----------

def test_audit_log_written(paper_env) -> None:
    from packages.paper import lifecycle

    audit = paper_env["audit"]
    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps, expired=True)
    lifecycle.tick(ps, {"BTCUSD": 100.5})  # time-stop close
    # duplicate blocked event
    _open(lifecycle, ps, symbol="ETHUSD", tf="1d", side="long")
    lifecycle.attempt_open(
        ps, symbol="ETHUSD", side="long", entry_price=60000.0,
        size_multiplier=1.0, timeframe="1d",
    )
    actions = [e["action"] for e in audit.read_recent()]
    assert "OPENED" in actions
    assert "CLOSED" in actions
    assert "OPEN_ATTEMPT" in actions
    assert "OPEN_BLOCKED" in actions
    summ = audit.summary()
    assert summ["window_events"] > 0 and summ["counts"].get("OPENED", 0) >= 1


def test_audit_read_skips_corrupt_lines(paper_env) -> None:
    audit = paper_env["audit"]
    p = paper_env["tmp"] / "paper_audit.jsonl"
    p.write_text('{"event_id":"a","action":"OPENED","timestamp":"t"}\n'
                 "{ broken json\n"
                 '{"event_id":"b","action":"CLOSED","timestamp":"t"}\n',
                 encoding="utf-8")
    events = audit.read_recent()
    assert [e["event_id"] for e in events] == ["a", "b"]  # bozuk satır atlandı


# ---------- learning handoff ----------

def test_closed_trade_carries_learning_fields(paper_env) -> None:
    from dataclasses import asdict

    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps, expired=True)
    closed = lifecycle.tick(ps, {"BTCUSD": 100.5})
    t = asdict(closed[0])
    for field in ("symbol", "timeframe", "opened_at", "closed_at", "open_reason",
                  "close_reason", "pnl_usd", "fingerprint", "snapshot_id",
                  "predicted_confidence", "lifecycle_status"):
        assert field in t, f"learning alanı eksik: {field}"
    assert t["open_reason"] == "unit-test"
    assert t["snapshot_id"] == "snap-1"


# ---------- state robustness ----------

def test_corrupt_state_backup_and_default(paper_env) -> None:
    paper_state = paper_env["state"]
    paper_state.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    paper_state.STATE_PATH.write_text("{ not valid json", encoding="utf-8")
    st = paper_state.load()  # crash YOK
    assert st.equity_usd > 0  # default state
    # yedek alındı + temiz dosya yazıldı
    backups = list(paper_env["tmp"].glob("paper_state.corrupt-*.json"))
    assert len(backups) == 1
    reloaded = json.loads(paper_state.STATE_PATH.read_text(encoding="utf-8"))
    assert reloaded["schema_version"] == paper_state.SCHEMA_VERSION
    # STATE_REPAIRED audit yazıldı
    assert any(e["action"] == "STATE_REPAIRED" for e in paper_env["audit"].read_recent())


def test_legacy_position_without_lifecycle_fields_loads(paper_env) -> None:
    paper_state = paper_env["state"]
    legacy = {
        "equity_usd": 10000.0,
        "peak_equity_usd": 10000.0,
        "open_positions": [{
            "id": "old1", "symbol": "BTCUSD", "side": "long",
            "entry_price": 100.0, "current_price": 100.0, "size_usd": 500.0,
            "sl": 96.0, "tp": 108.0, "opened_at": "2026-06-13T00:00:00+00:00",
            "timeframe": "1d",
            # lifecycle/learning alanları YOK + bilinmeyen ekstra alan:
            "legacy_unknown_field": "ignored",
        }],
        "recent_trades": [],
    }
    paper_state.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    paper_state.STATE_PATH.write_text(json.dumps(legacy), encoding="utf-8")
    st = paper_state.load()
    assert len(st.open_positions) == 1
    p = st.open_positions[0]
    assert p.lifecycle_status == "OPEN"     # default'a düştü
    assert p.scale_in is False
    assert p.open_reason is None


def test_atomic_save_no_tmp_left(paper_env) -> None:
    paper_state = paper_env["state"]
    ps = paper_state._initial_state()
    paper_state.save(ps)
    assert not list(paper_env["tmp"].glob("*.tmp*"))
    assert paper_state.STATE_PATH.exists()


# ---------- endpoint surface + no live dependency ----------

def test_state_endpoint_surfaces_lifecycle_and_audit(paper_env, monkeypatch) -> None:
    """GET /paper-trading/state additive alanları döner ve live pipeline ÇAĞIRMAZ."""
    from packages.data.ingestion import pipeline as pl
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    _open(lifecycle, ps)
    paper_env["state"].save(ps)

    # Import the app/router BEFORE patching. The router does
    # `from ...pipeline import get_cached_snapshot`, copying the value by reference
    # at import time. If we patched `pl` first and the app were imported here for the
    # first time, the router would freeze `_boom` into its OWN binding — which
    # monkeypatch never owns, so it would leak into later tests (e.g. test_halt's
    # tick). Importing first makes the router bind the real function; we then patch
    # the router's binding too, and monkeypatch restores every setattr on teardown.
    from apps.api.main import app
    from apps.api.routers import paper_trading as pt_router

    def _boom(*a, **k):
        raise AssertionError("state read attempted live data refetch")

    monkeypatch.setattr(pl, "get_cached_snapshot", _boom)
    monkeypatch.setattr(pl, "build_snapshot", _boom)
    monkeypatch.setattr(pt_router, "get_cached_snapshot", _boom)

    r = TestClient(app).get("/api/v1/paper-trading/state")
    assert r.status_code == 200
    body = r.json()
    assert "new_entries_disabled" in body
    assert "duplicate_warning" in body
    assert "audit_summary" in body
    assert "recent_audit_events" in body
    assert body["open_positions"][0]["lifecycle_status"] == "OPEN"


def test_risk_plan_update_long_success_and_audit(paper_env) -> None:
    from apps.api.main import app
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    pos = _open(lifecycle, ps, symbol="BTCUSD", side="long", entry=100.0)
    pos.current_price = 110.0
    paper_env["state"].save(ps)

    r = TestClient(app).patch(
        f"/api/v1/paper-trading/positions/{pos.id}/risk-plan",
        json={"sl": 105.0, "tp": 125.0},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "updated"
    assert body["paper_safe"] is True
    assert body["no_execution"] is True
    loaded = paper_env["state"].load()
    assert loaded.open_positions[0].sl == 105.0
    assert loaded.open_positions[0].tp == 125.0
    assert any(
        e["action"] == "MANUAL_RISK_PLAN_UPDATE"
        for e in paper_env["audit"].read_recent()
    )


def test_risk_plan_update_rejects_invalid_long_sl(paper_env) -> None:
    from apps.api.main import app
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    pos = _open(lifecycle, ps, symbol="BTCUSD", side="long", entry=100.0)
    pos.current_price = 110.0
    paper_env["state"].save(ps)

    r = TestClient(app).patch(
        f"/api/v1/paper-trading/positions/{pos.id}/risk-plan",
        json={"sl": 112.0, "tp": 125.0},
    )

    assert r.status_code == 400
    assert r.json()["reason"] == "LONG pozisyonda stop loss current/entry fiyatının altında olmalı."


def test_risk_plan_update_short_success_and_rejects_invalid_tp(paper_env) -> None:
    from apps.api.main import app
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    pos = _open(lifecycle, ps, symbol="ETHUSD", side="short", entry=100.0)
    pos.current_price = 90.0
    paper_env["state"].save(ps)

    client = TestClient(app)
    ok = client.patch(
        f"/api/v1/paper-trading/positions/{pos.id}/risk-plan",
        json={"sl": 98.0, "tp": 82.0},
    )
    assert ok.status_code == 200

    bad = client.patch(
        f"/api/v1/paper-trading/positions/{pos.id}/risk-plan",
        json={"sl": 98.0, "tp": 95.0},
    )
    assert bad.status_code == 400
    assert bad.json()["reason"] == "SHORT pozisyonda take profit current/entry fiyatının altında olmalı."


def test_risk_plan_update_rejects_non_number_and_closed_position(paper_env) -> None:
    from apps.api.main import app
    from packages.paper import lifecycle

    ps = paper_env["state"]._initial_state()
    pos = _open(lifecycle, ps, symbol="XAUUSD", side="long", entry=100.0)
    pos.current_price = 110.0
    paper_env["state"].save(ps)
    client = TestClient(app)

    bad_number = client.patch(
        f"/api/v1/paper-trading/positions/{pos.id}/risk-plan",
        json={"sl": "abc", "tp": None},
    )
    assert bad_number.status_code == 400
    assert bad_number.json()["reason"] == "SL geçerli bir sayı olmalı."

    ps = paper_env["state"].load()
    closed_trade = lifecycle.close_position(ps, ps.open_positions[0], exit_price=111.0, reason="MANUAL")
    paper_env["state"].save(ps)

    closed = client.patch(
        f"/api/v1/paper-trading/positions/{closed_trade.id}/risk-plan",
        json={"sl": 105.0, "tp": 125.0},
    )
    assert closed.status_code == 400
    assert closed.json()["reason"] == "Pozisyon kapalı olduğu için risk planı güncellenemez."
