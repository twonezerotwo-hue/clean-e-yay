"""17 Kasım P0 — sohbetten kâğıt işlemi onay koduyla; pozisyon işlemleri RiskGate'ten geçer.

Önce bu testler eski kodda düştü: soru cümlesi pozisyon kapatıyor/ters çeviriyordu,
scale-in ve flip RiskGate'e sormuyordu, ortalama giriş yanlıştı, sayı olmayan ya da
sıfır tutar kabul ediliyordu.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from packages.agent.llm import chat as llm_chat
from packages.ops import compliance
from packages.paper import manual_order, position_ops
from packages.paper import state as paper_state

# ---------- ortak kurulum ----------

@pytest.fixture
def llm_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "budget.json"))
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("LLM_LOAD_DOTENV", "false")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("COMPLIANCE_LOG_PATH", str(tmp_path / "compliance_log.jsonl"))
    monkeypatch.setattr(llm_chat, "_PENDING_ORDER", None)
    monkeypatch.setattr(llm_chat, "_PROPOSALS", {})
    return tmp_path


@pytest.fixture
def calls(monkeypatch):
    """Kâğıt durumunu değiştiren çağrıları say (gerçekte çalıştırmadan)."""
    seen: list[tuple[str, tuple, dict]] = []

    def _fake(name, result):
        def _f(*a, **k):
            seen.append((name, a, k))
            return result
        return _f

    monkeypatch.setattr(position_ops, "partial_close", _fake("partial_close", {
        "position_id": "p1", "symbol": "ETHUSD", "closed_usd": 500.0, "pnl_usd": 1.0, "remaining_usd": 500.0}))
    monkeypatch.setattr(position_ops, "flip", _fake("flip", {
        "closed_pnl_usd": 0.0, "new_position_id": "p2", "symbol": "BTCUSD", "new_side": "short",
        "size_usd": 1000.0, "entry_price": 100.0}))
    for name in ("set_trailing", "scale_in", "modify_sltp"):
        monkeypatch.setattr(position_ops, name, _fake(name, {}))
    monkeypatch.setattr(manual_order, "place", _fake("place", {
        "kind": "market", "side": "long", "symbol": "BTCUSD", "size_usd": 10000.0,
        "entry_price": 100.0, "sl": 95.0, "tp": 110.0, "position_id": "pos-test"}))
    for name in ("cancel", "cancel_all"):
        monkeypatch.setattr(manual_order, name, _fake(name, 1))
    monkeypatch.setattr(manual_order, "list_pending", lambda: [])
    return seen


def _ask(message: str, history: list[dict] | None = None) -> dict:
    return llm_chat.answer(message, history=history)


def _code(result: dict) -> str:
    m = re.match(r"Onay kodu (\d{4})\.", result["answer"])
    assert m, result["answer"]
    return m.group(1)


def _history(result: dict, user: str) -> list[dict]:
    """İstemcinin gönderdiği geçmiş: her tur ilk 500 karakter."""
    return [{"role": "user", "text": user}, {"role": "agent", "text": result["answer"][:500]}]


def _chat_rows() -> list[dict]:
    path = Path(os.environ["COMPLIANCE_LOG_PATH"])
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [r for r in rows if r.get("action") == "CHAT_COMMAND"]


# ---------- 1. soru cümlesi asla işlem değildir ----------

@pytest.mark.parametrize("question", [
    "ETH pozisyonunu yarıya kadar satmalı mıyım?",
    "BTC 4h ters çevirir mi sence",
    "gümüşte %50 kapatsam mı",
    "XAUUSD pozisyonumu büyütmeli miyim",
    "bekleyen emirleri iptal etsem mi?",
])
def test_question_never_proposes_or_trades(llm_env, calls, question):
    result = _ask(question)
    assert calls == []
    assert not any(e.endswith(":proposed") for e in result["evidence_used"])
    assert not result["answer"].startswith("Onay kodu")


# ---------- 2. komut önce öneri olur, onay kodu tek kullanımlıktır ----------

def test_command_becomes_proposal_and_confirm_runs_once(llm_env, calls):
    first = _ask("ETH'nin yarısını kapat")
    assert "pos_op:proposed" in first["evidence_used"]
    assert calls == []                                   # öneri işlem değildir
    code = _code(first)
    history = _history(first, "ETH'nin yarısını kapat")

    done = _ask(f"onayla {code}", history)
    assert [c[0] for c in calls] == ["partial_close"]
    assert calls[0][2] == {"fraction": 0.5, "size_usd": None}
    assert "pos_op:partial" in done["evidence_used"]

    again = _ask(f"onayla {code}", history)             # tekrar gönderim
    assert "confirm:invalid" in again["evidence_used"]
    assert [c[0] for c in calls] == ["partial_close"]    # ikinci işlem yok


def test_code_from_another_chat_is_refused(llm_env, calls):
    first = _ask("BTC'yi ters çevir")
    code = _code(first)
    other = [{"role": "user", "text": "merhaba"}, {"role": "agent", "text": "Merhaba, buyrun."}]
    refused = _ask(f"onayla {code}", other)
    assert "confirm:foreign" in refused["evidence_used"]
    assert calls == []
    # Önerinin göründüğü sohbet hâlâ onaylayabilir.
    _ask(f"onayla {code}", _history(first, "BTC'yi ters çevir"))
    assert [c[0] for c in calls] == ["flip"]


def test_expired_code_is_refused(llm_env, calls):
    first = _ask("BTC'yi ters çevir")
    code = _code(first)
    llm_chat._PROPOSALS[code]["ts"] -= llm_chat._PROPOSAL_TTL_SEC + 1
    result = _ask(f"onayla {code}", _history(first, "BTC'yi ters çevir"))
    assert "confirm:invalid" in result["evidence_used"]
    assert calls == []


def test_manual_order_needs_code_and_is_audited_with_original_command(llm_env, calls):
    first = _ask("btc'ye 10 bin al")
    assert "manual_order:proposed" in first["evidence_used"]
    assert calls == [] and _chat_rows() == []            # öneri kayda girmez
    code = _code(first)
    _ask(f"onayla {code}", _history(first, "btc'ye 10 bin al"))
    assert [c[0] for c in calls] == ["place"]
    rows = _chat_rows()
    assert len(rows) == 1 and rows[0]["outcome"] == "ok"
    assert rows[0]["detail"] == {"result": "manual_order:pos-test",
                                 "message": f"btc'ye 10 bin al (onayla {code})"}
    assert compliance.verify()["chain_ok"] is True


def test_cancel_all_needs_code(llm_env, calls):
    first = _ask("bekleyen emirlerin hepsini iptal et")
    assert "pending:proposed" in first["evidence_used"]
    assert calls == []
    _ask(f"onayla {_code(first)}", _history(first, "bekleyen emirlerin hepsini iptal et"))
    assert [c[0] for c in calls] == ["cancel_all"]


def test_side_follow_up_also_needs_code(llm_env, calls):
    asked = _ask("btc 10 bin emir")
    assert "manual_order:need_side" in asked["evidence_used"]
    proposal = _ask("al")
    assert "manual_order:proposed" in proposal["evidence_used"]
    assert calls == []


# ---------- 3. pozisyon işlemleri: RiskGate, doğru ortalama, sayı doğrulaması ----------

@pytest.fixture
def book(tmp_path, monkeypatch):
    """Tek açık BTC long (1000 $ @ 100); fiyat 50, DQS 95 (RiskGate serbest)."""
    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper.json")
    market = {"price": 50.0, "dqs": 95.0}

    def _market(_symbol):
        snap = SimpleNamespace(quality=SimpleNamespace(score=market["dqs"]), snapshot_id="snap-test")
        return market["price"], snap

    monkeypatch.setattr(position_ops, "_market_price", _market)
    st = paper_state.load()
    st.open_positions.append(paper_state.Position(
        id="p1", symbol="BTCUSD", side="long", entry_price=100.0, current_price=100.0,
        size_usd=1000.0, sl=90.0, tp=120.0, opened_at="2026-11-17T00:00:00+00:00", timeframe="1h",
    ))
    paper_state.save(st)
    return market


def _position() -> paper_state.Position | None:
    return next((p for p in paper_state.load().open_positions if p.id == "p1"), None)


def test_scale_in_average_entry_is_quantity_weighted(book):
    r = position_ops.scale_in("p1", 1000.0)              # 10 adet @100 + 20 adet @50
    assert r["size_usd"] == 2000.0
    assert r["avg_entry"] == pytest.approx(2000.0 / 30.0, abs=1e-3)   # 66,67; eskisi 75


def test_scale_in_and_flip_are_blocked_by_riskgate(book):
    book["dqs"] = 40.0                                   # DQS < 55 → KILL_SWITCH
    with pytest.raises(position_ops.PositionOpError, match="RiskGate"):
        position_ops.scale_in("p1", 500.0)
    with pytest.raises(position_ops.PositionOpError, match="RiskGate"):
        position_ops.flip("p1")
    pos = _position()                                    # yarım kalmış flip yok
    assert pos is not None and pos.side == "long" and pos.size_usd == 1000.0
    assert paper_state.load().recent_trades == []


@pytest.mark.parametrize("bad", [math.nan, math.inf, 0.0, -5.0])
def test_bad_amounts_change_nothing(book, bad):
    with pytest.raises(position_ops.PositionOpError):
        position_ops.scale_in("p1", bad)
    with pytest.raises(position_ops.PositionOpError):
        position_ops.partial_close("p1", size_usd=bad)
    with pytest.raises(position_ops.PositionOpError):
        position_ops.partial_close("p1", fraction=bad)
    with pytest.raises(position_ops.PositionOpError):
        position_ops.modify_sltp("p1", sl=bad)
    with pytest.raises(position_ops.PositionOpError):
        position_ops.set_trailing("p1", distance_pct=bad)
    pos = _position()
    assert pos.size_usd == 1000.0 and pos.sl == 90.0 and pos.trail_distance_pct is None
    assert paper_state.load().recent_trades == []        # sıfır boyutlu işlem kaydı yok


def test_partial_close_rounding_to_zero_is_refused(book):
    with pytest.raises(position_ops.PositionOpError, match="sıfıra"):
        position_ops.partial_close("p1", size_usd=0.001)
    assert paper_state.load().recent_trades == []


def test_partial_close_still_works(book):
    r = position_ops.partial_close("p1", fraction=0.5)
    assert r["closed_usd"] == 500.0 and r["remaining_usd"] == 500.0


def test_manual_order_rejects_non_finite_size(monkeypatch):
    monkeypatch.setattr(manual_order, "build_snapshot", lambda: pytest.fail("fiyat çekilmemeli"))
    for bad in (math.nan, math.inf):
        with pytest.raises(manual_order.ManualOrderError, match="sayı"):
            manual_order.place(symbol="BTCUSD", side="long", size_usd=bad)
    with pytest.raises(manual_order.ManualOrderError, match="fiyat"):
        manual_order.place(symbol="BTCUSD", side="long", size_usd=100.0, entry_price=math.nan)


# ---------- D5 (22 Kasım 2026): tek stop/hedef denetimi, tek sıfırlama yolu, tek düşüş ----------

def test_chat_sltp_on_wrong_side_is_refused(book):
    """Eski kod: sohbet yolu taraf denetimi yapmıyordu; yanlış taraftaki stop bir sonraki
    tick'te pozisyonu kapatırdı."""
    with pytest.raises(position_ops.PositionOpError, match="LONG"):
        position_ops.modify_sltp("p1", sl=105.0)          # long'da güncel 100'ün üstünde stop
    with pytest.raises(position_ops.PositionOpError, match="LONG"):
        position_ops.modify_sltp("p1", tp=95.0)
    assert _position().sl == 90.0 and _position().tp == 120.0
    assert position_ops.modify_sltp("p1", sl=95.0)["sl"] == 95.0


def test_api_reset_archives_and_clears_halts(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper.json")
    monkeypatch.setenv("PAPER_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    from packages.risk import halt
    from packages.risk.engine import RiskInput
    st = paper_state.load()
    st.equity_usd = 90_000.0
    paper_state.save(st)
    halt.sync(RiskInput(dqs_score=100, equity_usd=90_000, peak_equity_usd=100_000,
                        daily_pnl_usd=0, open_position_count=0))
    assert halt.active_halts()
    from apps.api.main import app
    r = TestClient(app).post("/api/v1/paper-trading/reset")
    assert r.status_code == 200
    assert list((tmp_path / "archive").glob("paper_state_*.json"))
    assert halt.active_halts() == []
    assert paper_state.load().equity_usd == paper_state._initial_state().equity_usd


def test_state_summary_drawdown_counts_open_positions(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper.json")
    st = paper_state.load()
    st.equity_usd = st.peak_equity_usd = 100_000.0
    st.open_positions.append(paper_state.Position(
        id="p9", symbol="BTCUSD", side="long", entry_price=100.0, current_price=85.0,
        size_usd=60_000.0, sl=None, tp=None, opened_at="2026-11-17T00:00:00+00:00", timeframe="1d",
    ))
    paper_state.save(st)
    from apps.api.main import app
    body = TestClient(app).get("/api/v1/paper-trading/state").json()
    assert body["max_drawdown_pct"] == pytest.approx(0.09)   # eski: 0.0 (yalnız gerçekleşmiş)
