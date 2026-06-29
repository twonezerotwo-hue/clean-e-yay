"""T2 — timeframe consensus + decision matrix + paper time-stop testleri.

Hepsi offline (TEST_USE_MOCK fixture barları; live network yok).

- TF'e göre consensus farklılaşır; default "1d" davranışı birebir korunur.
- decide_matrix: 5 TF × symbol hücre; 1w asla open üretmez; 15m size ×0.25.
- RiskGate global: DQS BLOCKED / KILL_SWITCH / halt → tüm TF'ler blocked
  + matrix SUSPENDED.
- Paper: timeframe + valid_until gerçek; time-stop dolunca TIME_STOP_EXIT;
  legacy kayıtlar default "1d" / valid_until=None.
- Fingerprint TF segmenti: 15m hatası 1d kararını cezalandırmaz.
- Correlation: aynı sembol farklı TF pozisyonları birlikte sayılır.
"""
from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.ingestion.pipeline import build_snapshot
from packages.data.types import TechnicalSnapshot
from packages.decision.engine import decide_matrix, matrix_view
from packages.regime.classifier import classify
from packages.risk.engine import RiskInput


def _risk_in(ps=None, dqs: float = 90.0) -> RiskInput:
    return RiskInput(
        dqs_score=dqs,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=0,
        open_position_count=0,
    )


@pytest.fixture
def paper_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    from packages.paper import state as ps_mod
    importlib.reload(ps_mod)
    return ps_mod


# ---------------- consensus ----------------

def test_consensus_default_1d_backward_compatible() -> None:
    from packages.consensus.engine import build
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    a = build("BTCUSD", snap, regime)
    b = build("BTCUSD", snap, regime, "1d")
    assert a.score == b.score
    assert a.timeframe == "1d" and b.timeframe == "1d"


def test_consensus_differs_when_technicals_by_tf_differ() -> None:
    from packages.consensus.engine import build
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    # TF teknikleri elle farklılaştır: 15m çok bearish, 1d çok bullish.
    snap.technicals_by_tf["BTCUSD"]["15m"] = TechnicalSnapshot(
        symbol="BTCUSD", timeframe="15m", rsi=20.0, macd=-1.0, atr=1.0,
        ema_stack="bearish", score=10.0, status="OK",
    )
    snap.technicals_by_tf["BTCUSD"]["1d"] = TechnicalSnapshot(
        symbol="BTCUSD", timeframe="1d", rsi=80.0, macd=1.0, atr=1.0,
        ema_stack="bullish", score=90.0, status="OK",
    )
    c15 = build("BTCUSD", snap, regime, "15m")
    c1d = build("BTCUSD", snap, regime, "1d")
    assert c15.score < c1d.score
    assert c15.timeframe == "15m"


def test_consensus_degraded_technicals_neutral_touche() -> None:
    from packages.consensus.engine import build
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    snap.technicals_by_tf["BTCUSD"]["15m"] = TechnicalSnapshot(
        symbol="BTCUSD", timeframe="15m", score=95.0, status="DEGRADED",
    )
    c = build("BTCUSD", snap, regime, "15m")
    touche = next(m for m in c.modules if m.name == "touche")
    assert touche.score == 50.0  # DEGRADED → nötr, 95 skoru kullanılmaz
    assert any("degraded" in w for w in c.warnings)


def test_consensus_degraded_technicals_dampens_direction_score() -> None:
    from packages.consensus.engine import build
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    snap.technicals_by_tf["BTCUSD"]["15m"] = TechnicalSnapshot(
        symbol="BTCUSD",
        timeframe="15m",
        rsi=58.0,
        macd=0.4,
        atr=1.0,
        ema_stack=None,
        score=95.0,
        direction_score=80.0,
        status="DEGRADED",
        bars_used=120,
    )
    c = build("BTCUSD", snap, regime, "15m")
    touche = next(m for m in c.modules if m.name == "touche")
    assert touche.score == pytest.approx(74.0)
    assert any("touche_degraded_dampened" in w for w in c.warnings)
    assert any("raw=80.00" in w and "factor=0.80" in w for w in c.warnings)


# ---------------- decision matrix ----------------

def _force_bullish(snap, symbol: str = "BTCUSD") -> None:
    """Tüm TF tekniklerini güçlü bullish yap (eşikler kesin aşılsın)."""
    for tf in ("15m", "1h", "4h", "1d", "1w"):
        snap.technicals_by_tf[symbol][tf] = TechnicalSnapshot(
            symbol=symbol, timeframe=tf, rsi=85.0, macd=2.0, atr=1.0,
            ema_stack="bullish", score=95.0, status="OK",
        )
    snap.technicals[symbol] = snap.technicals_by_tf[symbol]["1d"]


def test_matrix_produces_all_timeframes_and_1w_never_opens(paper_env, monkeypatch) -> None:
    # Konsantrasyon-dışı (1w/TF enum) test → intra_batch guard'ı kapat (ayrı testlerde).
    from packages.decision import engine as de
    monkeypatch.setattr(de, "_intra_batch_guard_enabled", lambda: False)
    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    _regime, _risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    by_tf = {d.timeframe: d for d in decisions}
    assert set(by_tf.keys()) == {"15m", "1h", "4h", "1d", "1w"}
    w = by_tf["1w"]
    assert w.action == "hold"  # paper_execution=false — sadece bias
    assert w.candidate_action in {"open_long", "open_short", "hold"}
    assert "timeframe_policy:no_paper_execution" in w.blocked_by
    assert w.actionable is False


def test_matrix_timeframe_risk_multiplier_only_reduces(paper_env, monkeypatch) -> None:
    # TF risk çarpanı testi → intra_batch guard kapalı (konsantrasyon ayrı testlerde).
    from packages.decision import engine as de
    monkeypatch.setattr(de, "_intra_batch_guard_enabled", lambda: False)
    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    _regime, _risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    by_tf = {d.timeframe: d for d in decisions}
    d1d, d15, d1h = by_tf["1d"], by_tf["15m"], by_tf["1h"]
    assert d1d.action == "open_long"
    assert d15.action == "open_long"
    # 15m ×0.25, 1h ×0.5 — hiçbir TF 1d'den büyük olamaz.
    assert d15.size_multiplier == pytest.approx(d1d.size_multiplier * 0.25, rel=1e-6)
    assert d1h.size_multiplier == pytest.approx(d1d.size_multiplier * 0.5, rel=1e-6)
    assert d15.size_multiplier <= d1d.size_multiplier


def test_matrix_1w_bearish_bias_scales_down_lower_tf_long(
    paper_env, monkeypatch
) -> None:
    # Deterministik: consensus'u TF'e göre sabitle — 1w güçlü bearish,
    # diğer TF'ler güçlü bullish.
    from packages.consensus.engine import ConsensusResult
    from packages.decision import engine as de
    # 1w-bias testi → intra_batch guard kapalı (konsantrasyon ayrı testlerde).
    monkeypatch.setattr(de, "_intra_batch_guard_enabled", lambda: False)

    def fake_build(symbol, snap, regime, timeframe="1d"):
        bearish = timeframe == "1w"
        return ConsensusResult(
            symbol=symbol,
            score=10.0 if bearish else 90.0,
            direction="bearish" if bearish else "bullish",
            modules=[],
            confluence_aligned=True,
            dominant_module="touche",
            timeframe=timeframe,
        )

    monkeypatch.setattr(de, "build_consensus", fake_build)
    snap = build_snapshot(["BTCUSD"])
    _regime, _risk, base = de.decide_matrix(
        ["BTCUSD"], snap, _risk_in(), timeframes=["1d"]
    )
    _regime, _risk, full = de.decide_matrix(["BTCUSD"], snap, _risk_in())
    d1d_alone = base[0]
    d1d = next(d for d in full if d.timeframe == "1d")
    w = next(d for d in full if d.timeframe == "1w")
    assert d1d_alone.action == "open_long"
    assert w.consensus.direction == "bearish" and w.action == "hold"
    # 1w bias çelişkisi → ×0.5 scale-down (asla artırma yok).
    assert "1w_bias_conflict:scale_down" in d1d.blocked_by
    assert d1d.size_multiplier == pytest.approx(
        d1d_alone.size_multiplier * 0.5, rel=1e-6
    )


def test_matrix_dqs_blocked_all_cells_blocked_suspended(paper_env) -> None:
    snap = build_snapshot(["BTCUSD", "ETHUSD"])
    _force_bullish(snap)
    regime, risk, decisions = decide_matrix(
        ["BTCUSD", "ETHUSD"], snap, _risk_in(dqs=30.0)  # DQS<55 → KILL_SWITCH
    )
    assert risk.action == "KILL_SWITCH"
    assert all(d.action == "blocked" for d in decisions)
    assert all(f"risk_gate:{risk.action}" in d.blocked_by for d in decisions)
    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD", "ETHUSD"])
    assert view["suspended"] is True
    assert all(c["status"] == "SUSPENDED" for c in view["cells"])
    assert all(c["actionable"] is False for c in view["cells"])
    assert all(c["paper_action"] == "none" for c in view["cells"])


def test_matrix_active_halt_blocks_all_timeframes(paper_env, monkeypatch) -> None:
    # Aktif DAILY_LOSS halt'i persist et → risk engine KILL_SWITCH.
    from packages.risk import halt as halt_store
    halt_store.sync(
        RiskInput(
            dqs_score=90.0,
            equity_usd=90_000,
            peak_equity_usd=100_000,
            daily_pnl_usd=-10_000,  # %3 limitin çok üstünde günlük zarar
            open_position_count=0,
        )
    )
    assert halt_store.active_halts(), "halt persist edilmeliydi"
    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    _regime, risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    assert risk.action == "KILL_SWITCH"
    assert all(d.action == "blocked" for d in decisions)


def test_matrix_view_actionable_cell_shape(paper_env) -> None:
    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    regime, risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"])
    assert view["symbols"] == ["BTCUSD"]
    assert view["timeframes"] == ["15m", "1h", "4h", "1d", "1w"]
    cell_1d = next(c for c in view["cells"] if c["timeframe"] == "1d")
    for key in (
        "action", "candidate_action", "blocked_by", "reason",
        "actionable", "status", "paper_action", "score", "direction",
        "warnings",
    ):
        assert key in cell_1d
    if cell_1d["actionable"]:
        assert cell_1d["status"] == "ACTIONABLE"
        assert cell_1d["paper_action"] == cell_1d["action"]


# ---------------- learning: TF-aware fingerprint ----------------

def test_fingerprint_tf_segment_isolates_15m_mistakes(paper_env) -> None:
    from packages.learning import mistake_memory
    from packages.learning.fingerprint import make

    fp15 = make(symbol="BTCUSD", regime="NEUTRAL", direction="bullish",
                score=72.0, confluence=True, dominant_module="touche",
                timeframe="15m")
    fp1d = make(symbol="BTCUSD", regime="NEUTRAL", direction="bullish",
                score=72.0, confluence=True, dominant_module="touche",
                timeframe="1d")
    assert fp15 != fp1d and "|15m|" in fp15 and "|1d|" in fp1d

    # 15m fingerprint'inde 3 kayıp → AVOID; aynı setup 1d'de NEUTRAL kalır.
    class _T:
        def __init__(self, fp, pnl, i):
            self.fingerprint = fp
            self.pnl_usd = pnl
            self.closed_at = f"2026-06-0{i}T00:00:00+00:00"
            self.data_verified = True
            self.symbol = "BTCUSD"
    trades = [_T(fp15, -100.0, i + 1) for i in range(3)]
    mems = mistake_memory._aggregate(trades)
    assert mistake_memory.evaluate(fp15, mems).action == "AVOID"
    assert mistake_memory.evaluate(fp1d, mems).action == "NEUTRAL"


def test_decision_fingerprint_carries_timeframe(paper_env) -> None:
    snap = build_snapshot(["BTCUSD"])
    _regime, _risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    for d in decisions:
        assert d.fingerprint is not None
        assert d.fingerprint.split("|")[2] == d.timeframe


# ---------------- paper: time-stop + legacy ----------------

def test_open_position_sets_timeframe_and_valid_until(paper_env) -> None:
    from packages.paper.lifecycle import open_position
    s = paper_env.load()
    pos = open_position(
        s, symbol="BTCUSD", side="long", entry_price=100.0,
        size_multiplier=1.0, timeframe="15m",
    )
    assert pos.timeframe == "15m"
    assert pos.valid_until is not None
    delta = datetime.fromisoformat(pos.valid_until) - datetime.now(UTC)
    assert timedelta(hours=5) < delta <= timedelta(hours=6)  # 15m → 6sa


def test_time_stop_exit_on_expiry(paper_env) -> None:
    from packages.paper.lifecycle import open_position, tick
    s = paper_env.load()
    open_position(
        s, symbol="BTCUSD", side="long", entry_price=100.0,
        size_multiplier=1.0, timeframe="15m",
    )
    future = datetime.now(UTC) + timedelta(hours=7)  # 6sa stop doldu
    trades = tick(s, {"BTCUSD": 100.5}, now=future)
    assert trades and trades[0].close_reason == "TIME_STOP_EXIT"
    assert trades[0].timeframe == "15m"
    assert s.open_positions == []


def test_time_stop_requires_price(paper_env) -> None:
    from packages.paper.lifecycle import open_position, tick
    s = paper_env.load()
    open_position(
        s, symbol="BTCUSD", side="long", entry_price=100.0,
        size_multiplier=1.0, timeframe="15m",
    )
    future = datetime.now(UTC) + timedelta(hours=7)
    trades = tick(s, {}, now=future)  # fiyat yok → kapatma yok (mock yok)
    assert trades == []
    assert len(s.open_positions) == 1


def test_legacy_position_loads_default_1d_no_valid_until(paper_env) -> None:
    legacy = {
        "id": "p1", "symbol": "BTCUSD", "side": "long",
        "entry_price": 100.0, "current_price": 101.0, "size_usd": 1000.0,
        "sl": 96.0, "tp": 108.0, "opened_at": "2026-06-01T00:00:00+00:00",
    }
    pos = paper_env.Position(**legacy)
    assert pos.timeframe == "1d"
    assert pos.valid_until is None
    # valid_until=None → time-stop hiç tetiklenmez.
    from packages.paper.lifecycle import _time_stop_due
    assert _time_stop_due(pos, datetime.now(UTC) + timedelta(days=365)) is False


def test_1d_position_no_time_stop_within_window(paper_env) -> None:
    from packages.paper.lifecycle import open_position, tick
    s = paper_env.load()
    open_position(
        s, symbol="BTCUSD", side="long", entry_price=100.0,
        size_multiplier=1.0, timeframe="1d",
    )
    soon = datetime.now(UTC) + timedelta(hours=24)  # 1d stop 672sa
    trades = tick(s, {"BTCUSD": 100.5}, now=soon)
    assert trades == []
    assert len(s.open_positions) == 1


# ---------------- correlation: aynı sembol farklı TF ----------------

def test_same_symbol_different_tf_counts_in_cluster(paper_env) -> None:
    from packages.paper.lifecycle import open_position
    from packages.risk.correlation import cluster_exposure
    s = paper_env.load()
    p1 = open_position(
        s, symbol="BTCUSD", side="long", entry_price=100.0,
        size_multiplier=1.5, timeframe="1d",
    )
    p2 = open_position(
        s, symbol="BTCUSD", side="long", entry_price=100.0,
        size_multiplier=1.5, timeframe="4h",
    )
    report = cluster_exposure([p1, p2], "BTCUSD", "long", equity_usd=100_000)
    # Aynı sembol → rho=1.0; iki TF pozisyonu da cluster üyesi.
    assert {m.position_id for m in report.members} == {p1.id, p2.id}
    assert report.cluster_pct > 0


# ---------------- endpoint ----------------

def test_decision_matrix_endpoint(paper_env) -> None:
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()

    from fastapi.testclient import TestClient

    from apps.api.main import app

    client = TestClient(app)
    r = client.get("/api/v1/decision/matrix")
    assert r.status_code == 200
    body = r.json()
    assert body["timeframes"] == ["15m", "1h", "4h", "1d", "1w"]
    assert len(body["cells"]) == len(body["symbols"]) * 5
    for c in body["cells"]:
        assert c["status"] in {"ACTIONABLE", "NOT_ACTIONABLE", "SUSPENDED"}
        if c["timeframe"] == "1w":
            assert c["action"] != "open_long" and c["action"] != "open_short"
    assert "risk_gate" in body and "dqs_status" in body and "mode" in body


def test_paper_tick_endpoint_timeframe_actions(paper_env) -> None:
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()

    from fastapi.testclient import TestClient

    from apps.api.main import app

    client = TestClient(app)
    r = client.post("/api/v1/paper-trading/tick")
    assert r.status_code == 200
    body = r.json()
    assert body["actions"], "her (symbol, tf) için aksiyon raporlanmalı"
    # Tüm aksiyonlar timeframe taşır; 1w'de open asla yok.
    for a in body["actions"]:
        assert "timeframe" in a
        if a["timeframe"] == "1w":
            assert a["action"] != "open"
    # Açılan pozisyonlar timeframe + valid_until taşır.
    state = client.get("/api/v1/paper-trading/state").json()
    for p in state["open_positions"]:
        assert p["timeframe"] in {"15m", "1h", "4h", "1d"}
        assert p["valid_until"] is not None


# ---------------- intra-batch yığılma koruması ----------------

def _fake_open(symbol, snap, regime, risk, *, mistakes=None, open_positions=None,
               equity_usd=0.0, corr_entries=None, timeframe="1d"):
    """Her hücreyi open_short olarak döndürür; gördüğü open_positions uzunluğunu
    çağıran teste kaydetmek için _fake_open.seen listesine ekler."""
    from packages.consensus.engine import ConsensusResult
    from packages.decision.engine import TradeDecision
    _fake_open.seen.append(len(open_positions or []))
    cons = ConsensusResult(
        symbol=symbol, score=42.0, direction="bearish", modules=[],
        confluence_aligned=False, dominant_module="touche", timeframe=timeframe,
    )
    return TradeDecision(
        symbol=symbol, action="open_short", confidence=0.5, size_multiplier=0.5,
        consensus=cons, risk=risk, reason="t", timeframe=timeframe,
    )


def test_decide_matrix_feeds_pass_siblings_when_guard_on(monkeypatch) -> None:
    # guard AÇIK: pass içinde açılan kardeşler büyüyen open_positions'a eklenir →
    # sonraki hücre daha uzun liste görür (correlation cap onları görebilir).
    from packages.decision import engine
    monkeypatch.setattr(engine, "_intra_batch_guard_enabled", lambda: True)
    _fake_open.seen = []
    monkeypatch.setattr(engine, "decide_for_symbol", _fake_open)
    snap = build_snapshot(["BTCUSD"])
    engine.decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["15m", "1h", "4h"])
    assert _fake_open.seen == [0, 1, 2]  # her açılış sonrakine birikiyor


def test_decide_matrix_guard_off_is_old_blind_behavior(monkeypatch) -> None:
    # guard KAPALI (default): kardeşler beslenmez → her hücre pass-başı snapshot'ı görür.
    from packages.decision import engine
    monkeypatch.setattr(engine, "_intra_batch_guard_enabled", lambda: False)
    _fake_open.seen = []
    monkeypatch.setattr(engine, "decide_for_symbol", _fake_open)
    snap = build_snapshot(["BTCUSD"])
    engine.decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["15m", "1h", "4h"])
    assert _fake_open.seen == [0, 0, 0]  # körlük: kimse kardeşini görmez


def test_open_decisions_carry_expected_value(paper_env, monkeypatch) -> None:
    # F5 — açık kararlar expected_value (gözlem) taşımalı (ev_gate KAPALI olsa da).
    from packages.decision import engine as de
    monkeypatch.setattr(de, "_intra_batch_guard_enabled", lambda: False)
    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    _regime, _risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    opens = [d for d in decisions if d.action in ("open_long", "open_short")]
    assert opens, "force_bullish en az bir açık üretmeli"
    for d in opens:
        assert d.expected_value is not None  # F5 gözlem alanı dolu


def test_matrix_view_cells_expose_expected_value(paper_env) -> None:
    # F5 gözlem: matrix_view hücreleri expected_value taşımalı (dashboard için).
    snap = build_snapshot(["BTCUSD"])
    _regime, _risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    vm = matrix_view(_regime, _risk, decisions, snap, ["BTCUSD"])
    assert vm["cells"], "hücre üretilmeli"
    for c in vm["cells"]:
        assert "expected_value" in c  # alan her hücrede var (None olabilir)
