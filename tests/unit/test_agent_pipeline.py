"""Step 7 — agent pipeline composer tests (wiring + cost/R:R overlay).

Deterministic: per-TF results are constructed directly (no bars/network) so the
composition agent → consensus → decision → economics gate is exercised in
isolation. Covers RiskGate dominance, the DATA_POLICY no-fabricated-entry path,
the aligned SCOUT happy path, and the FINAL cost/R:R overlay that downgrades a
SCOUT whose economics fail.
"""
from __future__ import annotations

from packages.data.types import (
    ConfirmationSignal,
    TechnicalDataQuality,
    TechnicalKeyLevels,
    TechnicalScoreOverview,
    TechnicalTimeframeResult,
    TechnicalTimeframeSummary,
    Timeframe,
)
from packages.decision import agent_pipeline as ap


def _tf(
    timeframe: Timeframe,
    *,
    bias: str = "BULLISH",
    direction: float = 70.0,
    strength: float = 70.0,
    fired: bool = True,
    stop: float | None = None,
    target: float | None = None,
) -> TechnicalTimeframeResult:
    return TechnicalTimeframeResult(
        symbol="BTCUSD",
        timeframe=timeframe,
        data_quality=TechnicalDataQuality(status="OK", bars_used=300),
        score_overview=TechnicalScoreOverview(direction_score=direction, strength_score=strength),
        key_levels=TechnicalKeyLevels(stop_reference=stop, target_reference=target),
        confirmation_signals=[ConfirmationSignal(name="trigger", fired=fired)],
        timeframe_summary=TechnicalTimeframeSummary(bias=bias),  # type: ignore[arg-type]
    )


def _aligned_bull(*, stop: float | None = None, target: float | None = None) -> dict:
    """d1 + h1 both confirmed BULLISH → consensus ALIGNED, SCOUT entry on 1h."""
    return {"1d": _tf("1d"), "1h": _tf("1h", stop=stop, target=target)}


# ── RiskGate is final (TF-agnostic) ───────────────────────────────────────────

def test_kill_switch_dominates():
    v = ap.build_symbol_view(
        "BTCUSD", _aligned_bull(stop=99.5, target=101.0),
        current_price=100.0, risk_action="KILL_SWITCH",
    )
    assert v.decision.action == "KILL_SWITCH"
    assert v.decision.size_multiplier == 0.0
    assert v.economics is None  # no entry on a kill-switch decision


# ── DATA_POLICY: empty inputs never fabricate an entry ────────────────────────

def test_empty_bars_no_fabricated_entry():
    v = ap.build_symbol_view_from_bars("BTCUSD", {tf: [] for tf in ap.PIPELINE_TFS})
    assert v.agent.stance in {"ABSTAIN", "DEGRADED"}
    assert v.decision.action in {"NO_TRADE", "WATCH"}
    assert v.decision.size_multiplier == 0.0
    assert v.economics is None


# ── Aligned setup with viable economics → SCOUT ───────────────────────────────

def test_aligned_setup_is_scout_when_economics_ok():
    # entry 100, stop 99.5 (50bps), target 101 (100bps): rr 2.0, net edge 75.
    v = ap.build_symbol_view(
        "BTCUSD", _aligned_bull(stop=99.5, target=101.0), current_price=100.0,
    )
    assert v.decision.action == "SCOUT_ALLOWED"
    assert v.decision.entry_timeframe == "1h"
    assert v.decision.size_multiplier == 0.5  # 1h base cap; never boosted
    assert v.economics is not None and v.economics.allow is True


# ── FINAL cost/R:R overlay downgrades a SCOUT whose economics fail ────────────

def test_economics_gate_downgrades_scout_on_bad_rr():
    # entry 100, stop 99.40 (60bps), target 100.60 (60bps): rr 1.0 < 1.5.
    v = ap.build_symbol_view(
        "BTCUSD", _aligned_bull(stop=99.40, target=100.60), current_price=100.0,
    )
    assert v.economics is not None and v.economics.allow is False
    assert v.economics.reason == "bad_rr"
    assert v.decision.action == "WATCH"  # downgraded — never forced through
    assert v.decision.size_multiplier == 0.0
    assert any(b.startswith("risk:economics:") for b in v.decision.blocking_agents)


def test_economics_gate_downgrades_scout_below_cost():
    # entry 100, stop 99.85 (15bps), target 100.30 (30bps): rr 2.0 ok, net 5 < 20.
    v = ap.build_symbol_view(
        "BTCUSD", _aligned_bull(stop=99.85, target=100.30), current_price=100.0,
    )
    assert v.economics is not None and v.economics.reason == "below_cost"
    assert v.decision.action == "WATCH"


def test_missing_levels_block_scout():
    # SCOUT but no stop/target → gate blocks (no entry without defined risk).
    v = ap.build_symbol_view("BTCUSD", _aligned_bull(), current_price=100.0)
    assert v.economics is not None and v.economics.reason == "insufficient_levels"
    assert v.decision.action == "WATCH"


# ── ViewModel shape (frontend does no math) ───────────────────────────────────

def test_matrix_viewmodel_shape():
    v = ap.build_symbol_view(
        "BTCUSD", _aligned_bull(stop=99.5, target=101.0),
        current_price=100.0, risk_action="HOLD",
    )
    vm = ap.matrix_viewmodel([v], risk_action="HOLD")
    assert vm["risk_action"] == "HOLD"
    assert vm["timeframes"][0] == "15m"
    row = vm["symbols"][0]
    assert row["symbol"] == "BTCUSD"
    assert {"stance", "consensus", "decision", "economics"} <= set(row)
    assert row["economics"]["allow"] is True


# ── Determinism (timestamps excepted) ─────────────────────────────────────────

def test_deterministic_decision_ignoring_ts():
    per_tf = _aligned_bull(stop=99.5, target=101.0)
    a = ap.build_symbol_view("BTCUSD", per_tf, current_price=100.0)
    b = ap.build_symbol_view("BTCUSD", per_tf, current_price=100.0)
    assert (a.decision.action, a.decision.size_multiplier, a.decision.entry_timeframe) == (
        b.decision.action, b.decision.size_multiplier, b.decision.entry_timeframe,
    )
    assert a.economics == b.economics
