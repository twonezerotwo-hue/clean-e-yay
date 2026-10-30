"""Fikir onayı → paper pozisyon (owner tıklaması). Ağa ÇIKMAZ, gerçek broker emri YOK.

Güvenceler:
- Onay yalnız MEVCUT `manual_order.place` yolundan paper pozisyon açar; RiskGate/günlük zarar/maks.
  pozisyon bypass EDİLEMEZ; gerçek neden kullanıcıya döner.
- Çift tıklama/yarışta (ardışık ya da eşzamanlı) yalnız TEK pozisyon açılır.
- Eski sinyal, çelişen yön, aynı sembolde açık pozisyon/bekleyen emir, veri/fiyat yokluğu → açılmaz.
- Açılan pozisyon `owner_idea` ile MANUAL kohorttadır (otomatik kalibrasyona sızmaz).
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.paper import idea_order, manual_order
from packages.paper import state as paper_state
from packages.paper.state import PendingOrder, Position

SYMBOL = "BTCUSD"


def _now() -> datetime:
    return datetime.now(UTC)


def make_idea(symbol: str = SYMBOL, **over) -> dict:
    idea = {
        "symbol": symbol, "kind": "crypto", "name": "Bitcoin", "score": 72,
        "components": {"technical": 30.0, "scorecard": 10.0, "news": 15.0, "risk": 0.0},
        "status": "WATCHING", "status_label": "izleniyor",
        "technical": {
            "verdict": "WOULD_OPEN_LONG", "entry_timeframe": "1h", "confidence": 0.4,
            "checked_at": (_now() - timedelta(minutes=30)).isoformat(), "bullish_tfs": ["1h", "4h"],
        },
        "scorecard": {"signals": 10, "resolved": 8, "decisive": 6},
        "news": {"direction": "up", "strength": 60, "n_headlines": 3},
        "risk_notes": [],
    }
    idea.update(over)
    return idea


def _quote(symbol: str = SYMBOL, price: float = 60_000.0, dqs: float = 90.0) -> SimpleNamespace:
    return SimpleNamespace(
        snapshot_id="snap-test",
        prices=[SimpleNamespace(symbol=symbol, price=price, verified=True)],
        quality=SimpleNamespace(score=dqs),
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """İzole defter + fikir panosu + ağsız veri ön-koşulları (hepsi 'sağlıklı')."""
    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper.json")
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("IDEA_BOARD_PATH", str(tmp_path / "idea_board.json"))
    board = tmp_path / "idea_board.json"

    def write_board(*ideas: dict) -> None:
        board.write_text(json.dumps({"generated_at": _now().isoformat(), "ideas": list(ideas)}),
                         encoding="utf-8")

    write_board(make_idea())
    monkeypatch.setattr(manual_order, "build_snapshot", lambda: _quote())
    monkeypatch.setattr(idea_order.snapshot_store, "latest", lambda: {
        "generated_at": (_now() - timedelta(seconds=10)).isoformat(), "dqs": {"score": 90.0}})
    monkeypatch.setattr(idea_order.price_provider, "has_live_source", lambda s: True)
    monkeypatch.setattr(idea_order.price_sanity, "ohlcv_reference_price", lambda s, tf: (60_000.0, "ohlcv:1h"))
    monkeypatch.setattr(idea_order.price_sanity, "price_sane_with_ohlcv_reason", lambda *a, **k: None)
    monkeypatch.setattr(idea_order, "evaluate_session", lambda *a, **k: SimpleNamespace(
        route="open", effective_multiplier=1.0, decision=SimpleNamespace(reason="")))
    return SimpleNamespace(write_board=write_board, tmp=tmp_path)


def positions() -> list[Position]:
    return paper_state.load().open_positions


def seed_position(symbol: str, size_usd: float = 1_000.0) -> None:
    with paper_state.transaction("test:seed") as ps:
        ps.open_positions.append(Position(
            id=f"seed-{symbol}", symbol=symbol, side="long", entry_price=100.0, current_price=100.0,
            size_usd=size_usd, sl=None, tp=None, opened_at=_now().isoformat(), timeframe="1d"))


# ------------------------------------------------------------------ onay → paper açılış

def test_confirm_opens_one_paper_position_through_the_manual_order_path(env):
    res = idea_order.open_from_idea(SYMBOL)
    assert res["status"] == "opened" and res["state"] == "OPENED"
    pos = res["position"]
    assert pos["symbol"] == SYMBOL and pos["side"] == "long" and pos["entry_price"] == 60_000.0
    assert pos["size_usd"] == 6_250.0                       # 25_000 × 0.25 (yalnız KÜÇÜLEN çarpanlar)
    assert pos["position_id"] and pos["opened_at"] and pos["timeframe"] == "1h"
    assert pos["sl"] is not None and pos["tp"] is not None  # sistemin risk planı
    (opened,) = positions()
    assert opened.id == pos["position_id"] and opened.open_reason == "owner_idea"
    assert opened.tier == "MANUAL" and opened.data_verified is True


def test_idea_positions_are_manual_cohort_so_they_never_leak_into_auto_learning():
    from packages.learning import cohorts
    from packages.learning.outcomes import CanonicalOutcome

    oc = CanonicalOutcome(
        trade_id="t", symbol=SYMBOL, timeframe="1h", opened_at=None, closed_at=None, duration_seconds=None,
        direction="long", open_price=None, close_price=None, pnl=1.0, pnl_pct=None,
        open_reason=idea_order.OPEN_REASON, close_reason="TP_HIT", fingerprint=None, regime="NEUTRAL",
        dominant_module=None, candidate_action=None, final_action=None, data_verified=True)
    assert cohorts.classify(oc) == cohorts.MANUAL


def test_double_click_sequential_second_request_is_refused(env):
    first = idea_order.open_from_idea(SYMBOL)
    second = idea_order.open_from_idea(SYMBOL)
    assert first["status"] == "opened"
    assert second["status"] == "blocked" and second["state"] == "ALREADY_OPEN"
    assert first["position"]["position_id"] in second["reason"]
    assert len(positions()) == 1


def test_double_click_concurrent_requests_open_exactly_one_position(env):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: idea_order.open_from_idea(SYMBOL), range(8)))
    assert sum(r["status"] == "opened" for r in results) == 1
    assert all(r["state"] == "ALREADY_OPEN" for r in results if r["status"] == "blocked")
    assert len(positions()) == 1


def test_open_position_on_the_same_symbol_blocks_even_on_another_timeframe_or_side(env):
    with paper_state.transaction("test:seed") as ps:
        ps.open_positions.append(Position(
            id="p-short-4h", symbol=SYMBOL, side="short", entry_price=1.0, current_price=1.0,
            size_usd=500.0, sl=None, tp=None, opened_at=_now().isoformat(), timeframe="4h"))
    res = idea_order.open_from_idea(SYMBOL)
    assert res["status"] == "blocked" and res["state"] == "ALREADY_OPEN"
    assert len(positions()) == 1                           # yalnız seed


def test_pending_order_on_the_symbol_also_blocks(env):
    with paper_state.transaction("test:seed") as ps:
        ps.pending_orders.append(PendingOrder(
            id="o1", symbol=SYMBOL, side="long", size_usd=100.0, order_type="limit",
            trigger_price=50_000.0, limit_price=None, created_at=_now().isoformat(), timeframe="1d",
            reason="owner_manual"))
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "ALREADY_OPEN" and "bekleyen emir" in res["reason"]
    assert positions() == []


# ------------------------------------------------------------------ RiskGate ve limitler bypass edilemez

def test_low_data_quality_riskgate_blocks_with_the_real_reason(env, monkeypatch):
    monkeypatch.setattr(manual_order, "build_snapshot", lambda: _quote(dqs=40.0))
    res = idea_order.open_from_idea(SYMBOL)
    assert res["status"] == "blocked" and res["state"] == "RISK_BLOCKED"
    assert "RiskGate engelledi" in res["reason"] and "KILL_SWITCH" in res["reason"]
    assert positions() == []


def test_daily_loss_limit_blocks_new_idea_positions(env):
    with paper_state.transaction("test:loss") as ps:
        ps.daily_anchor_date = _now().date().isoformat()
        ps.daily_pnl_usd = -0.03 * ps.equity_usd           # limit %2
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "RISK_BLOCKED" and "Günlük zarar" in res["reason"]
    assert positions() == []


def test_max_open_positions_limit_blocks(env):
    for i in range(6):
        seed_position(f"SYM{i}")
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "RISK_BLOCKED" and "NO_POSITION_INCREASE" in res["reason"]
    assert len(positions()) == 6


def test_total_exposure_above_equity_blocks(env):
    seed_position("SYM0", size_usd=paper_state.load().equity_usd - 100.0)
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "RISK_BLOCKED" and "maruziyet" in res["reason"]
    assert len(positions()) == 1


def test_active_halt_blocks(env, monkeypatch):
    from packages.risk import halt as halt_store

    monkeypatch.setattr(halt_store, "active_halts", lambda: [SimpleNamespace(
        type="DAILY_LOSS", level="RISK_REDUCE", reason="halt", evidence=[])])
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "RISK_BLOCKED"
    assert positions() == []


def test_session_gate_block_is_reported_with_its_reason(env, monkeypatch):
    monkeypatch.setattr(idea_order, "evaluate_session", lambda *a, **k: SimpleNamespace(
        route="block", effective_multiplier=0.0, decision=SimpleNamespace(reason="piyasa kapalı")))
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "RISK_BLOCKED" and "piyasa kapalı" in res["reason"]
    assert positions() == []


def test_session_caution_multiplier_only_shrinks_the_size(env, monkeypatch):
    monkeypatch.setattr(idea_order, "evaluate_session", lambda *a, **k: SimpleNamespace(
        route="open", effective_multiplier=0.5, decision=SimpleNamespace(reason="")))
    assert idea_order.open_from_idea(SYMBOL)["position"]["size_usd"] == 3_125.0


def test_correlation_cluster_cap_blocks(env, monkeypatch):
    monkeypatch.setattr(idea_order.correlation, "cluster_exposure", lambda *a, **k: SimpleNamespace(
        size_factor=0.0, cluster_pct=0.45, max_cluster_pct=0.30))
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "RISK_BLOCKED" and "korelasyon" in res["reason"]
    assert positions() == []


def test_state_anomaly_blocks(env):
    with paper_state.transaction("test:anomaly") as ps:
        ps.equity_usd = 10 ** 12                           # absürt defter
    res = idea_order.open_from_idea(SYMBOL)
    assert res["status"] == "blocked"
    assert positions() == []


# ------------------------------------------------------------------ sinyal geçerliliği

def test_expired_signal_is_refused(env):
    stale = make_idea()
    stale["technical"]["checked_at"] = (_now() - timedelta(hours=6)).isoformat()
    env.write_board(stale)
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "SIGNAL_EXPIRED" and "önce üretildi" in res["reason"]
    assert positions() == []


def test_signal_validity_follows_the_scanner_refresh_cadence_not_a_single_bar():
    assert idea_order.signal_max_age("1h") == timedelta(hours=4)    # tarama ritmi (result_ttl_sec)
    assert idea_order.signal_max_age("1d") == timedelta(hours=24)   # bir bar daha uzunsa bar


@pytest.mark.parametrize("override,needle", [
    ({"technical": {"verdict": "NO_SIGNAL", "entry_timeframe": "1h",
                    "checked_at": "2999-01-01T00:00:00+00:00"}}, "teknik teyit yok"),
    ({"news": {"direction": "down", "strength": 70, "n_headlines": 2}}, "çelişen"),
    ({"technical": {"verdict": "WOULD_OPEN_LONG", "entry_timeframe": "1w",
                    "checked_at": "2999-01-01T00:00:00+00:00"}}, "uygun değil"),
])
def test_invalid_signal_is_refused(env, override, needle):
    env.write_board(make_idea(**override))
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "NO_SIGNAL" and needle in res["reason"]
    assert positions() == []


def test_unknown_idea_is_refused(env):
    res = idea_order.open_from_idea("NOPEUSD")
    assert res["status"] == "blocked" and res["state"] == "NO_IDEA"


# ------------------------------------------------------------------ veri / fiyat

def test_symbol_without_live_price_source_waits_for_data_with_the_real_reason(env, monkeypatch):
    monkeypatch.setattr(idea_order.price_provider, "has_live_source", lambda s: False)
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "DATA_UNAVAILABLE" and "canlı fiyat kaynağı" in res["reason"]
    assert positions() == []


def test_missing_ohlcv_reference_waits_for_data(env, monkeypatch):
    monkeypatch.setattr(idea_order.price_sanity, "ohlcv_reference_price", lambda s, tf: (None, None))
    assert idea_order.open_from_idea(SYMBOL)["state"] == "DATA_UNAVAILABLE"


def test_stale_system_snapshot_waits_for_data(env, monkeypatch):
    monkeypatch.setattr(idea_order.snapshot_store, "latest", lambda: {
        "generated_at": (_now() - timedelta(minutes=10)).isoformat(), "dqs": {"score": 90.0}})
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "DATA_UNAVAILABLE" and "eski" in res["reason"]


def test_live_quote_missing_at_order_time_is_data_unavailable_not_a_fake_price(env, monkeypatch):
    monkeypatch.setattr(manual_order, "build_snapshot", lambda: _quote(symbol="ETHUSD"))
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "DATA_UNAVAILABLE" and "güncel fiyat yok" in res["reason"]
    assert positions() == []


def test_board_verdict_blocks_when_snapshot_has_no_current_quote(env, monkeypatch):
    monkeypatch.setattr(idea_order.snapshot_store, "latest", lambda: {
        "generated_at": (_now() - timedelta(seconds=10)).isoformat(),
        "data_snapshot": {"prices": []},
        "dqs": {"score": 90.0},
    })
    view = idea_order.annotate_board({"generated_at": _now().isoformat(), "ideas": [make_idea()]})
    verdict = view["ideas"][0]["paper_open"]
    assert verdict["state"] == "DATA_UNAVAILABLE"
    assert "güncel fiyat yok" in verdict["reason"]


def test_insane_quote_is_refused(env, monkeypatch):
    monkeypatch.setattr(idea_order.price_sanity, "price_sane_with_ohlcv_reason",
                        lambda *a, **k: "ohlcv:1h_jump_40pct_gt_10pct")
    res = idea_order.open_from_idea(SYMBOL)
    assert res["state"] == "DATA_UNAVAILABLE" and "tutarsiz" in res["reason"]
    assert positions() == []


# ------------------------------------------------------------------ /ideas ön-durumu (ağsız)

def test_annotate_board_marks_a_healthy_idea_ready_and_blocked_ones_with_reasons(env):
    stale = make_idea("ETHUSD")
    stale["technical"]["checked_at"] = (_now() - timedelta(hours=9)).isoformat()
    view = idea_order.annotate_board({"generated_at": _now().isoformat(), "ideas": [make_idea(), stale]})
    ready, expired = (i["paper_open"] for i in view["ideas"])
    assert ready["state"] == "READY" and ready["can_open"] is True and ready["size_usd"] == 6_250.0
    assert ready["side"] == "long" and ready["timeframe"] == "1h" and ready["expires_at"]
    assert expired["state"] == "SIGNAL_EXPIRED" and expired["can_open"] is False and expired["reason"]


def test_annotate_board_reports_riskgate_and_already_open_before_any_click(env):
    seed_position(SYMBOL)
    view = idea_order.annotate_board({"generated_at": _now().isoformat(), "ideas": [make_idea()]})
    po = view["ideas"][0]["paper_open"]
    assert po["state"] == "ALREADY_OPEN" and po["position_id"] == f"seed-{SYMBOL}"

    for i in range(5):
        seed_position(f"SYM{i}")
    other = make_idea("ETHUSD")
    po2 = idea_order.annotate_board({"generated_at": _now().isoformat(), "ideas": [other]})["ideas"][0]["paper_open"]
    assert po2["state"] == "RISK_BLOCKED" and "NO_POSITION_INCREASE" in po2["reason"]


def test_annotate_board_with_no_ideas_is_a_noop(env):
    view = {"generated_at": None, "ideas": []}
    assert idea_order.annotate_board(view) == {"generated_at": None, "ideas": []}


def test_annotate_board_never_opens_anything(env):
    idea_order.annotate_board({"generated_at": _now().isoformat(), "ideas": [make_idea()]})
    assert positions() == [] and paper_state.load().pending_orders == []


# ------------------------------------------------------------------ manual_order geriye uyumluluk

def test_manual_order_default_behaviour_is_unchanged(env):
    res = manual_order.place(SYMBOL, "long", 2_000.0)
    assert res["kind"] == "market" and res["opened_at"]
    assert positions()[0].open_reason == "owner_manual"


def test_manual_order_guard_runs_inside_the_lock_and_can_stop_the_open(env):
    def refuse(ps, size_usd):
        raise manual_order.ManualOrderError("guard durdurdu", 409, reason="guard")

    with pytest.raises(manual_order.ManualOrderError, match="guard durdurdu"):
        manual_order.place(SYMBOL, "long", 2_000.0, guard=refuse)
    assert positions() == []


def test_manual_order_errors_carry_machine_readable_reasons(env, monkeypatch):
    monkeypatch.setattr(manual_order, "build_snapshot", lambda: _quote(dqs=40.0))
    with pytest.raises(manual_order.ManualOrderError) as exc:
        manual_order.place(SYMBOL, "long", 2_000.0)
    assert exc.value.reason == "risk_gate"


# ------------------------------------------------------------------ NO_EXECUTION / API

def test_no_broker_is_touched_and_paper_safe_flags_hold(env, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app

    for name in ("place_order", "submit_order", "execute_order"):
        assert not hasattr(idea_order, name) and not hasattr(manual_order, name)
    client = TestClient(app)
    r = client.post(f"/api/v1/paper-trading/ideas/{SYMBOL}/open")
    assert r.status_code == 200 and r.json()["status"] == "opened"
    health = client.get("/api/v1/system/health").json()
    assert health["paper_safe"] is True and health["no_execution"] is True


def test_open_endpoint_returns_200_with_state_and_reason_for_blocked(env):
    from fastapi.testclient import TestClient

    from apps.api.main import app

    client = TestClient(app)
    client.post(f"/api/v1/paper-trading/ideas/{SYMBOL}/open")
    again = client.post(f"/api/v1/paper-trading/ideas/{SYMBOL}/open")
    body = again.json()
    assert again.status_code == 200 and body["status"] == "blocked"
    assert body["state"] == "ALREADY_OPEN" and body["reason"]
    assert len(positions()) == 1


def test_ideas_endpoint_exposes_paper_open_for_each_idea(env):
    from fastapi.testclient import TestClient

    from apps.api.main import app

    body = TestClient(app).get("/api/v1/ideas").json()
    (idea,) = body["ideas"]
    assert idea["paper_open"]["state"] == "READY" and idea["paper_open"]["can_open"] is True
