"""Phase 2d — signal attribution / closed-trade decision log tests.

Acceptance (audit + learning only — attribution NEVER opens/sizes/decides):
- every paper close writes exactly one structured decision_log record;
- the opening signal (reason, fingerprint, snapshot, DQS, RiskGate) is preserved;
- the exit reason and timeframe are preserved;
- missing snapshot / risk / DQS / source metadata → diagnostics, never a crash;
- a decision_log write failure NEVER blocks the trade close (best-effort);
- recording carries the PAPER_SAFE / NO_EXECUTION contract and triggers no trade.
"""
from __future__ import annotations

import pytest

from packages.learning import decision_log


@pytest.fixture
def att_env(tmp_path, monkeypatch):
    """Isolated paper state + audit + decision-log paths (no real-file writes)."""
    from packages.paper import audit
    from packages.paper import state as paper_state

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper_state.json")
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "paper_audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    return {"state": paper_state, "audit": audit, "tmp": tmp_path}


def _open(lifecycle, ps, **over):
    """Open a fully-attributed BTC long unless a field is overridden to None."""
    kw = dict(
        symbol="BTCUSD", side="long", entry_price=100.0, size_multiplier=1.0,
        timeframe="4h", open_reason="breakout-long", snapshot_id="snap-1",
        fingerprint="fp-1", open_dqs=87.5, open_risk_action="ALLOW",
    )
    kw.update(over)
    return lifecycle.open_position(ps, **kw)


# ---------- 1. close writes a record ----------

def test_close_writes_decision_record(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps)
    lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    rows = decision_log.read_recent()
    assert len(rows) == 1
    assert rows[0]["trade_id"] == pos.id
    assert rows[0]["symbol"] == "BTCUSD"
    assert rows[0]["outcome"]["won"] is True
    assert rows[0]["record_id"] == f"{pos.id}:{rows[0]['closed_at']}"


# ---------- 2. opening signal + open reason preserved ----------

def test_open_reason_and_opening_signal_preserved(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps, open_reason="owner_approved:defensive")
    lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    sig = decision_log.read_recent()[0]["opening_signal"]
    assert sig["reason"] == "owner_approved:defensive"


# ---------- 3. exit reason preserved ----------

def test_exit_reason_preserved(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps)
    lifecycle.close_position(ps, pos, exit_price=90.0, reason="SL_HIT")
    rec = decision_log.read_recent()[0]
    assert rec["exit"]["reason"] == "SL_HIT"
    assert rec["outcome"]["won"] is False


# ---------- 4. fingerprint preserved ----------

def test_fingerprint_preserved(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps, fingerprint="btc|60|aligned")
    lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    assert decision_log.read_recent()[0]["opening_signal"]["fingerprint"] == "btc|60|aligned"


# ---------- 5. timeframe preserved ----------

def test_timeframe_preserved(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps, timeframe="15m")
    lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    assert decision_log.read_recent()[0]["timeframe"] == "15m"


# ---------- 6. snapshot id preserved when present ----------

def test_snapshot_id_preserved(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps, snapshot_id="snap-42")
    lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    rec = decision_log.read_recent()[0]
    assert rec["opening_signal"]["snapshot_id"] == "snap-42"
    assert "snapshot_id_missing" not in rec["diagnostics"]


# ---------- 7. missing snapshot id does not crash ----------

def test_missing_snapshot_id_does_not_crash(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps, snapshot_id=None)
    trade = lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    assert trade.id == pos.id  # close completed
    rec = decision_log.read_recent()[0]
    assert rec["opening_signal"]["snapshot_id"] is None
    assert "snapshot_id_missing" in rec["diagnostics"]


# ---------- 8. RiskGate fields preserved when present ----------

def test_risk_gate_action_preserved(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps, open_risk_action="REDUCE")
    lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    rec = decision_log.read_recent()[0]
    assert rec["opening_signal"]["risk_gate"] == "REDUCE"
    assert "risk_action_missing" not in rec["diagnostics"]


# ---------- 9. DQS fields preserved when present ----------

def test_dqs_preserved(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps, open_dqs=72.0)
    lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    rec = decision_log.read_recent()[0]
    assert rec["opening_signal"]["dqs"] == 72.0
    assert "dqs_missing" not in rec["diagnostics"]


# ---------- 10. missing risk/DQS/source metadata creates diagnostics ----------

def test_missing_metadata_creates_diagnostics(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(
        lifecycle, ps,
        snapshot_id=None, fingerprint=None,
        open_dqs=None, open_risk_action=None, open_reason=None,
    )
    lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    diag = decision_log.read_recent()[0]["diagnostics"]
    assert {"snapshot_id_missing", "fingerprint_missing", "dqs_missing",
            "risk_action_missing", "open_reason_missing"} <= set(diag)


# ---------- 11. write failure does not prevent trade close ----------

def test_write_failure_does_not_block_close(att_env, monkeypatch) -> None:
    from packages.paper import lifecycle

    # Point the log at a path whose parent is a regular file → mkdir/open raises
    # OSError on write. The close must still complete (best-effort attribution).
    bad_parent = att_env["tmp"] / "not_a_dir"
    bad_parent.write_text("x", encoding="utf-8")
    monkeypatch.setenv("DECISION_LOG_PATH", str(bad_parent / "decision_log.jsonl"))

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps)
    trade = lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")

    # Trade close fully succeeded despite the failed log write.
    assert not ps.open_positions
    assert ps.recent_trades and ps.recent_trades[-1].id == pos.id
    assert trade.pnl_usd > 0  # winning long (exit 110 > entry 100)
    # Nothing persisted to the bad path, but a write-failure audit warning was left.
    assert decision_log.read_recent() == []
    assert any(
        e.get("reason") == "decision_log_write_failed"
        for e in att_env["audit"].read_recent()
    )


# ---------- 12. attribution never opens/resizes/triggers trades ----------

def test_record_close_is_pure_no_trade_side_effects(att_env) -> None:
    """record_close takes only a Trade and persists it — it has no access to state,
    so it cannot open, resize, or close a position. The public surface is record/read
    only (no trade-mutating API)."""
    from packages.paper.state import Trade

    trade = Trade(
        id="t-1", symbol="BTCUSD", side="long", entry_price=100.0,
        exit_price=110.0, pnl_usd=10.0, opened_at="o", closed_at="c",
        close_reason="TP_HIT",
    )
    entry = decision_log.record_close(trade)
    assert entry["trade_id"] == "t-1"
    assert len(decision_log.read_recent()) == 1
    assert set(decision_log.__all__) == {"entry_for", "record_close", "read_recent", "summary"}


# ---------- safety contract stamped on every record ----------

def test_record_carries_paper_safe_no_execution(att_env) -> None:
    from packages.paper import lifecycle

    ps = att_env["state"]._initial_state()
    pos = _open(lifecycle, ps)
    lifecycle.close_position(ps, pos, exit_price=110.0, reason="TP_HIT")
    rec = decision_log.read_recent()[0]
    assert rec["paper_safe"] is True
    assert rec["no_execution"] is True
    assert rec["execution_mode"] == "PAPER"


# ---------- read tolerance: corrupt lines skipped ----------

def test_read_recent_skips_corrupt_lines(att_env) -> None:
    p = att_env["tmp"] / "decision_log.jsonl"
    p.write_text(
        '{"trade_id":"a","outcome":{"won":true}}\n'
        "{ broken json\n"
        '{"trade_id":"b","outcome":{"won":false}}\n',
        encoding="utf-8",
    )
    rows = decision_log.read_recent()
    assert [r["trade_id"] for r in rows] == ["a", "b"]
    summ = decision_log.summary()
    assert summ["window_trades"] == 2 and summ["wins"] == 1 and summ["losses"] == 1
