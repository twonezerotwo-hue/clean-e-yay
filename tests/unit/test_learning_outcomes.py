"""L1 — outcome learning loop testleri.

- dominant_module parse: v2 (parts[7]) / legacy (parts[5]) / malformed → fallback.
- canonical outcome: legacy + P1-enriched trade'den; eksik alan default, crash yok.
- timeframe-aware: 15m outcome 1d bucket'ını ETKİLEMEZ.
- auto-weight trainer v2 fingerprint'i doğru module'e atfeder (score_bucket'a değil).
- mistake memory timeframe ayırır (farklı tf → farklı kayıt).
- learning worker: boş veri → NO_DATA (crash yok) + metadata yazılır.

Testlerde live network yok (conftest TEST_USE_MOCK=true).
"""
from __future__ import annotations

import importlib

import pytest

V2 = "BTCUSD|v2|4h|OFFENSIVE|bullish|S55|C|touche"
LEGACY = "BTCUSD|NEUTRAL|bullish|S65|C|fundamental"


# ----------------------------- fingerprint parse -----------------------------

def test_dominant_module_v2_uses_parts7() -> None:
    from packages.learning import fingerprint as fp
    # parts[5]='S55' (score_bucket), parts[7]='touche' (gerçek module)
    assert fp.dominant_module(V2) == "touche"
    assert fp.parse(V2)["score_bucket"] == "S55"


def test_dominant_module_legacy_uses_parts5() -> None:
    from packages.learning import fingerprint as fp
    assert fp.dominant_module(LEGACY) == "fundamental"


def test_dominant_module_malformed_returns_none() -> None:
    from packages.learning import fingerprint as fp
    assert fp.dominant_module("x") is None
    assert fp.dominant_module(None) is None
    assert fp.dominant_module("BTCUSD|v2|4h") is None  # eksik v2 → None


def test_parse_v2_fields() -> None:
    from packages.learning import fingerprint as fp
    p = fp.parse(V2)
    assert p["version"] == "v2"
    assert p["timeframe"] == "4h"
    assert p["regime"] == "OFFENSIVE"
    assert p["direction"] == "bullish"
    assert p["dominant_module"] == "touche"


# ----------------------------- canonical outcome -----------------------------

def _trade(ps, **kw):
    defaults = dict(
        id="t1",
        symbol="BTCUSD",
        side="long",
        entry_price=100.0,
        exit_price=110.0,
        pnl_usd=50.0,
        opened_at="2026-06-11T00:00:00+00:00",
        closed_at="2026-06-11T02:00:00+00:00",
        close_reason="TP_HIT",
        fingerprint=V2,
        data_verified=True,
    )
    defaults.update(kw)
    return ps.Trade(**defaults)


def test_canonical_outcome_from_legacy_trade() -> None:
    from packages.learning import outcomes as om
    from packages.paper.state import Trade
    # Legacy: timeframe default "1d", open_reason/snapshot_id yok.
    t = Trade(
        id="leg1",
        symbol="XAUUSD",
        side="short",
        entry_price=2000.0,
        exit_price=1980.0,
        pnl_usd=40.0,
        opened_at="2026-06-11T00:00:00+00:00",
        closed_at="2026-06-11T01:00:00+00:00",
        close_reason="SL_HIT",
        fingerprint=LEGACY,
        data_verified=False,
    )
    o = om.build_outcome(t)
    assert o.timeframe == "1d"  # legacy default
    assert o.regime == "NEUTRAL"  # legacy parts[1]
    assert o.dominant_module == "fundamental"  # legacy parts[5]
    assert o.direction == "short"
    assert o.final_action == "open_short"
    assert o.candidate_action == "open_short"
    assert o.blocked_by == [] and o.gates_applied == []
    assert o.decision_id is None
    assert o.source_quality == "unverified"
    assert o.paper_only is True
    assert o.duration_seconds == 3600.0
    # short pnl_pct: entry 2000 → exit 1980 = +1% (short kazanç)
    assert o.pnl_pct == 1.0


def test_canonical_outcome_from_p1_enriched_trade() -> None:
    from packages.learning import outcomes as om
    from packages.paper.state import Trade
    t = Trade(
        id="p1",
        symbol="BTCUSD",
        side="long",
        entry_price=100.0,
        exit_price=110.0,
        pnl_usd=50.0,
        opened_at="2026-06-11T00:00:00+00:00",
        closed_at="2026-06-11T02:00:00+00:00",
        close_reason="TP_HIT",
        fingerprint=V2,
        data_verified=True,
        timeframe="15m",
        open_reason="consensus bullish",
        snapshot_id="snap-123",
        lifecycle_status="CLOSED",
    )
    o = om.build_outcome(t)
    assert o.timeframe == "15m"  # Trade.timeframe explicit
    assert o.regime == "OFFENSIVE"  # v2 parts[3]
    assert o.dominant_module == "touche"  # v2 parts[7]
    assert o.open_reason == "consensus bullish"
    assert o.snapshot_id == "snap-123"
    assert o.source_quality == "verified"
    assert o.final_action == "open_long"
    assert o.duration_seconds == 7200.0
    assert o.pnl_pct == 10.0  # long 100→110 = +10%


def test_build_outcome_never_crashes_on_garbage() -> None:
    from packages.learning import outcomes as om
    from packages.paper.state import Trade
    t = Trade(
        id="g",
        symbol="X",
        side="?",
        entry_price=0.0,  # bölme guard
        exit_price=0.0,
        pnl_usd=0.0,
        opened_at="not-a-date",
        closed_at="also-bad",
        close_reason="?",
        fingerprint="garbage|fp",
    )
    o = om.build_outcome(t)
    assert o.timeframe == "1d"
    assert o.dominant_module == "unknown"
    assert o.regime == "UNKNOWN"
    assert o.pnl_pct is None
    assert o.duration_seconds is None


# --------------------------- timeframe-aware bucket --------------------------

def test_15m_outcome_does_not_affect_1d_bucket() -> None:
    from packages.learning import outcomes as om
    from packages.paper.state import Trade

    def mk(tf: str, pnl: float, tid: str) -> Trade:
        return Trade(
            id=tid,
            symbol="BTCUSD",
            side="long",
            entry_price=100.0,
            exit_price=100.0 + (1 if pnl > 0 else -1),
            pnl_usd=pnl,
            opened_at="2026-06-11T00:00:00+00:00",
            closed_at="2026-06-11T01:00:00+00:00",
            close_reason="TP_HIT" if pnl > 0 else "SL_HIT",
            fingerprint=f"BTCUSD|v2|{tf}|NEUTRAL|bullish|S55|C|touche",
            data_verified=True,
            timeframe=tf,
        )

    # 15m hep kayıp, 1d hep kazanç
    trades = [mk("15m", -10, "a"), mk("15m", -10, "b"), mk("1d", 20, "c"), mk("1d", 20, "d")]
    outs = [om.build_outcome(t) for t in trades]
    bd = om.breakdowns(outs)
    assert bd["by_timeframe"]["15m"]["win_rate"] == 0.0
    assert bd["by_timeframe"]["1d"]["win_rate"] == 1.0
    assert bd["by_timeframe"]["15m"]["trades"] == 2
    assert bd["by_timeframe"]["1d"]["trades"] == 2
    # 1d bucket'ın toplam pnl'i 15m kayıplarından etkilenmez
    assert bd["by_timeframe"]["1d"]["total_pnl"] == 40.0


# --------------------------- trainer v2 attribution --------------------------

@pytest.fixture
def learn_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("REBALANCE_STORE_PATH", str(tmp_path / "rebalance.json"))
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(tmp_path / "weights_active.json"))
    monkeypatch.setenv("WEIGHTS_OUTPUT_DIR", str(tmp_path / "weights_out"))
    monkeypatch.setenv("LEARNING_RUN_PATH", str(tmp_path / "learning_run.json"))
    monkeypatch.setenv("LEARNING_OUT_PATH", str(tmp_path / "learning_summary.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    from packages.data.registry import loader as ld
    importlib.reload(ld)
    return ps, ld


def _seed_v2(ps, *, n: int, module: str = "touche", tf: str = "1d") -> None:
    state = ps.load()
    for i in range(n):
        state.recent_trades.append(
            ps.Trade(
                id=f"v{i}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=101.0,
                pnl_usd=120.0 if i % 2 == 0 else -50.0,
                opened_at="2026-06-11T00:00:00+00:00",
                closed_at="2026-06-11T01:00:00+00:00",
                close_reason="TP_HIT",
                fingerprint=f"BTCUSD|v2|{tf}|NEUTRAL|bullish|S55|C|{module}",
                data_verified=True,
                predicted_confidence=0.7,
                timeframe=tf,
            )
        )
    ps.save(state)


def test_trainer_attributes_v2_module_not_score_bucket(learn_env) -> None:
    ps, _ = learn_env
    _seed_v2(ps, n=10, module="touche", tf="1d")
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="NEUTRAL")
    assert hasattr(res, "evidence")
    modules = {p.module for p in res.evidence}
    assert "touche" in modules        # gerçek module
    assert "S55" not in modules       # score_bucket DEĞİL (eski bug)
    # timeframe/regime evidence proposal'da görünür
    audit = res.proposed_yaml["audit"]
    assert audit["timeframe_distribution"] == {"1d": 10}
    assert audit["module_distribution"] == {"touche": 10}


def test_trainer_insufficient_no_proposal(learn_env) -> None:
    ps, _ = learn_env
    _seed_v2(ps, n=4, module="touche")  # < MIN_TOTAL_TRADES
    from packages.learning import auto_weight_trainer as t
    res = t.train(regime="NEUTRAL")
    assert isinstance(res, dict)
    assert res["status"] == "INSUFFICIENT"


# ---------------------------- mistake memory by tf ---------------------------

def test_mistake_memory_separates_by_timeframe(learn_env) -> None:
    ps, _ = learn_env
    # Aynı symbol/regime/module ama farklı timeframe → ayrı fingerprint → ayrı kayıt
    _seed_v2(ps, n=4, module="touche", tf="15m")
    _seed_v2(ps, n=4, module="touche", tf="1d")
    from packages.learning import mistake_memory as mm
    mems = mm.summary()
    fps = {m.fingerprint for m in mems}
    assert any("|15m|" in f for f in fps)
    assert any("|1d|" in f for f in fps)
    assert len(mems) == 2  # 15m ve 1d ayrı bucket


# ------------------------------ learning worker ------------------------------

def test_learning_worker_empty_data_no_crash(learn_env) -> None:
    ps, _ = learn_env  # boş state
    from apps.learning_worker import main as lw
    importlib.reload(lw)
    run = lw.run_once()
    assert run["status"] == "NO_DATA"
    assert run["outcomes_seen"] == 0
    assert run["proposals_generated"] == 0
    assert run["errors"] == []
    assert run["skipped_reason"] == "no_closed_outcomes"
    # metadata persisted + summary endpoint görür
    from packages.learning import run_store
    saved = run_store.load()
    assert saved is not None
    assert saved["run_id"] == run["run_id"]


def test_learning_worker_metadata_with_data(learn_env) -> None:
    ps, ld = learn_env
    _seed_v2(ps, n=10, module="touche", tf="1d")
    from apps.learning_worker import main as lw
    importlib.reload(lw)
    run = lw.run_once()
    assert run["status"] in {"COMPLETED", "COMPLETED_WITH_ERRORS"}
    assert run["outcomes_seen"] == 10
    assert run["proposals_generated"] == 1
    assert run["calibration_status"] in {"INSUFFICIENT", "FITTED"}
    # Owner approval olmadan active weights DEĞİŞMEZ (proposal sadece PENDING).
    importlib.reload(ld)
    assert ld.active_weights_version() == "1.0.0"


def test_summary_surfaces_breakdowns_and_worker_run(learn_env) -> None:
    ps, _ = learn_env
    _seed_v2(ps, n=3, module="touche", tf="15m")
    _seed_v2(ps, n=3, module="touche", tf="1d")
    from packages.learning.summary import build_summary
    out = build_summary()
    assert out["outcomes_total"] == 6
    assert out["verified_outcomes"] == 6
    assert "15m" in out["by_timeframe"] and "1d" in out["by_timeframe"]
    assert out["by_dominant_module"]["touche"]["trades"] == 6
    assert out["proposal_status"] in {"NONE", "PENDING", "APPROVED", "REJECTED"}
