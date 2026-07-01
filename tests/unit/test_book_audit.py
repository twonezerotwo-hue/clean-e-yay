"""Açık-kitap yapısal denetimi (packages/learning/book_audit.py) + engine
self-conflict guard (shadow-first) testleri.

- Detektörler: self-conflict, yoğunlaşma, çok-TF kopya, tek-yön kitap.
- Aktif guard: flag KAPALI iken aday geçer (yalnız gözlem, active=False);
  flag AÇIK iken aynı sembolde zıt yön bloklanır.
- Endpoint: /api/v1/learning/book-audit yapısal özet döner.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def _pos(ps, *, symbol, side, size_usd, timeframe="1d", entry=100.0, pid="p"):
    return ps.Position(
        id=f"{pid}-{symbol}-{timeframe}-{side}",
        symbol=symbol,
        side=side,
        entry_price=entry,
        current_price=entry,
        size_usd=size_usd,
        sl=None,
        tp=None,
        opened_at="2026-06-11T00:00:00+00:00",
        timeframe=timeframe,
    )


# ---------------- detektörler ----------------

def test_self_conflict_detected(fresh_env) -> None:
    from packages.learning import book_audit
    ps = fresh_env
    positions = [
        _pos(ps, symbol="BRENT", side="short", size_usd=5_000, timeframe="4h"),
        _pos(ps, symbol="BRENT", side="long", size_usd=1_250, timeframe="15m"),
    ]
    lessons = book_audit.detect_self_conflict(positions)
    assert len(lessons) == 1
    assert lessons[0].code == "SELF_CONFLICT"
    assert lessons[0].severity == "CRITICAL"
    assert lessons[0].symbols == ["BRENT"]


def test_no_self_conflict_when_one_sided(fresh_env) -> None:
    from packages.learning import book_audit
    ps = fresh_env
    positions = [
        _pos(ps, symbol="BRENT", side="short", size_usd=5_000, timeframe="4h"),
        _pos(ps, symbol="BRENT", side="short", size_usd=1_250, timeframe="15m"),
    ]
    assert book_audit.detect_self_conflict(positions) == []


def test_concentration_flagged_over_threshold(fresh_env) -> None:
    from packages.learning import book_audit
    ps = fresh_env
    # XAG 17.5k / 25k book = %70 ≥ %30 eşiği → CRITICAL (≥ %39)
    positions = [
        _pos(ps, symbol="XAGUSD", side="short", size_usd=10_000, timeframe="4h"),
        _pos(ps, symbol="XAGUSD", side="short", size_usd=5_000, timeframe="1h"),
        _pos(ps, symbol="XAGUSD", side="short", size_usd=2_500, timeframe="15m"),
        _pos(ps, symbol="BTCUSD", side="short", size_usd=7_500, timeframe="1d"),
    ]
    lessons = book_audit.detect_concentration(positions, book_audit._cfg())
    codes = {(L.code, L.symbols[0]) for L in lessons}
    assert ("CONCENTRATION", "XAGUSD") in codes
    xag = next(L for L in lessons if L.symbols == ["XAGUSD"])
    assert xag.severity == "CRITICAL"


def test_multi_tf_stack_detected(fresh_env) -> None:
    from packages.learning import book_audit
    ps = fresh_env
    positions = [
        _pos(ps, symbol="XAUUSD", side="short", size_usd=5_000, timeframe="4h", entry=4038.9),
        _pos(ps, symbol="XAUUSD", side="short", size_usd=2_500, timeframe="1h", entry=4038.9),
        _pos(ps, symbol="XAUUSD", side="short", size_usd=1_250, timeframe="15m", entry=4038.9),
    ]
    lessons = book_audit.detect_multi_tf_stack(positions, book_audit._cfg())
    assert len(lessons) == 1
    assert lessons[0].code == "MULTI_TF_STACK"
    # aynı entry → kopya tespiti detail'da geçer
    assert "kopya" in lessons[0].detail.lower()


def test_one_way_book_flagged(fresh_env) -> None:
    from packages.learning import book_audit
    ps = fresh_env
    positions = [
        _pos(ps, symbol="XAUUSD", side="short", size_usd=5_000),
        _pos(ps, symbol="XAGUSD", side="short", size_usd=5_000),
        _pos(ps, symbol="BTCUSD", side="short", size_usd=5_000),
        _pos(ps, symbol="BRENT", side="long", size_usd=1_000),
    ]
    lessons = book_audit.detect_one_way(positions, book_audit._cfg())
    assert len(lessons) == 1
    assert lessons[0].code == "ONE_WAY_BOOK"
    assert "SHORT" in lessons[0].title


def test_clean_book_no_lessons(fresh_env) -> None:
    from packages.learning import book_audit
    ps = fresh_env
    positions = [
        _pos(ps, symbol="BTCUSD", side="long", size_usd=5_000),
        _pos(ps, symbol="NVDA", side="short", size_usd=5_000),
    ]
    assert book_audit.audit(positions, 100_000) == []


# ---------------- aktif self-conflict guard (shadow-first) ----------------

def _force_pass(monkeypatch):
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision import engine as dec
    from packages.regime.classifier import classify
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    fake = ConsensusResult(
        symbol="BTCUSD", score=85.0, direction="bullish", confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=85.0, weight=1.0, contribution=85.0)],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)
    return dec, snap, regime


def test_self_conflict_guard_off_allows_but_observes(fresh_env, monkeypatch) -> None:
    dec, snap, regime = _force_pass(monkeypatch)
    from packages.risk.engine import RiskDecision
    # guard default KAPALI — aynı sembolde zıt yön açık olsa bile aday geçer.
    monkeypatch.setattr(dec, "_self_conflict_cfg", lambda: {"enabled": False})
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    short_pos = _pos(fresh_env, symbol="BTCUSD", side="short", size_usd=5_000, timeframe="4h")
    d = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk, open_positions=[short_pos], equity_usd=100_000
    )
    assert d.action == "open_long"  # davranış değişmez
    assert d.self_conflict_report.get("active") is False
    assert d.self_conflict_report.get("open_opposite_side") == "short"


def test_self_conflict_guard_on_blocks(fresh_env, monkeypatch) -> None:
    dec, snap, regime = _force_pass(monkeypatch)
    from packages.risk.engine import RiskDecision
    monkeypatch.setattr(dec, "_self_conflict_cfg", lambda: {"enabled": True})
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    short_pos = _pos(fresh_env, symbol="BTCUSD", side="short", size_usd=5_000, timeframe="4h")
    d = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk, open_positions=[short_pos], equity_usd=100_000
    )
    assert d.action == "hold"
    assert "self_conflict_guard" in d.blocked_by
    assert d.self_conflict_report.get("active") is True


def test_self_conflict_guard_same_side_no_block(fresh_env, monkeypatch) -> None:
    """Aynı yön (long üstüne long) self-conflict DEĞİL — guard tetiklenmez."""
    dec, snap, regime = _force_pass(monkeypatch)
    from packages.risk.engine import RiskDecision
    monkeypatch.setattr(dec, "_self_conflict_cfg", lambda: {"enabled": True})
    # Concentration guard'ı izole et: aynı-yön yığınını O bloklar (kendi testinde);
    # burada YALNIZ self_conflict'in aynı-yönde tetiklenmediğini doğruluyoruz.
    monkeypatch.setattr(dec, "_concentration_cfg", lambda: {"enabled": False})
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    long_pos = _pos(fresh_env, symbol="BTCUSD", side="long", size_usd=5_000, timeframe="4h")
    d = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk, open_positions=[long_pos], equity_usd=100_000
    )
    assert d.action == "open_long"
    assert d.self_conflict_report == {}


# ---------------- endpoint ----------------

def test_chat_book_audit_answer_surfaces_lessons(fresh_env) -> None:
    from packages.agent.llm import chat
    ps = fresh_env
    state = ps.load()
    state.open_positions.append(
        _pos(ps, symbol="BRENT", side="short", size_usd=5_000, timeframe="4h", pid="a")
    )
    state.open_positions.append(
        _pos(ps, symbol="BRENT", side="long", size_usd=1_250, timeframe="15m", pid="b")
    )
    ps.save(state)
    ans, ev = chat._book_audit_answer()
    assert "BRENT" in ans
    assert any("SELF_CONFLICT" in e for e in ev)


def test_chat_book_audit_answer_clean(fresh_env) -> None:
    from packages.agent.llm import chat
    ans, ev = chat._book_audit_answer()
    assert "temiz" in ans.lower()
    assert ev == ["book_audit:clean"]


def test_book_audit_endpoint(fresh_env) -> None:
    ps = fresh_env
    state = ps.load()
    state.open_positions.append(
        _pos(ps, symbol="BRENT", side="short", size_usd=5_000, timeframe="4h", pid="a")
    )
    state.open_positions.append(
        _pos(ps, symbol="BRENT", side="long", size_usd=1_250, timeframe="15m", pid="b")
    )
    ps.save(state)

    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/learning/book-audit")
    assert r.status_code == 200
    body = r.json()
    assert body["open_positions"] == 2
    assert body["clean"] is False
    codes = {L["code"] for L in body["lessons"]}
    assert "SELF_CONFLICT" in codes
