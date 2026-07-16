"""Step 9 — shadow observation guard tests (Phase A, affect_decision:false).

The shadow layer runs the NEW agent pipeline alongside the live engine and records a
comparison. These tests pin the hard invariants: the activation gate requires BOTH
flags, observation never touches paper (no paper parameter, no paper import), the
agreement labels are deterministic, and every record is PAPER_SAFE/NO_EXECUTION
stamped with affected_paper=false.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from packages.decision import shadow


# ── stubs (no bars / network) ─────────────────────────────────────────────────

def _live(symbol, action, *, actionable=True, tf="1h", conf=0.6, size=0.5):
    return SimpleNamespace(
        symbol=symbol, action=action, actionable=actionable,
        timeframe=tf, confidence=conf, size_multiplier=size,
    )


def _view(symbol, *, action="WATCH", direction_score=50.0, entry_tf=None, size=0.0, stance="CAUTION"):
    return SimpleNamespace(
        symbol=symbol,
        decision=SimpleNamespace(action=action, entry_timeframe=entry_tf, size_multiplier=size),
        consensus=SimpleNamespace(direction_score=direction_score),
        agent=SimpleNamespace(stance=stance),
    )


def _cmp(live_decisions, views, cfg=None):
    return shadow.build_comparison(
        snapshot_id="snap-1", risk_action="HOLD",
        live_decisions=live_decisions, shadow_views=views,
        cfg=cfg or shadow.ShadowConfig(enabled=True, affect_decision=False),
    )


# ── activation gate: requires BOTH flags (Phase A keeps it closed) ────────────

def test_affects_paper_requires_both_flags():
    assert shadow.affects_paper(shadow.ShadowConfig(enabled=True, affect_decision=True)) is True
    assert shadow.affects_paper(shadow.ShadowConfig(enabled=True, affect_decision=False)) is False
    assert shadow.affects_paper(shadow.ShadowConfig(enabled=False, affect_decision=True)) is False


def test_default_config_is_disabled_observe_only():
    cfg = shadow.ShadowConfig()
    assert cfg.enabled is False and cfg.affect_decision is False
    assert cfg.manual_ready_only is True


def test_committed_config_phase_b_manual_ready_only():
    # 2026-07-16 FAZ-2 "erken açılış" (ROADMAP_10_10 Dalga-2): sevk edilen config
    # Phase B — affect_decision açık AMA manual_ready_only DEĞİŞMEZ garanti:
    # girişler yalnız owner-onay kuyruğuna düşer (oto-açılış yolu yok; mimari
    # bekçi test_shadow_activation_only_queues_manual_ready kaynak-metinde doğrular).
    cfg = shadow.load_config()
    assert cfg.enabled is True
    assert cfg.affect_decision is True
    assert cfg.manual_ready_only is True
    assert shadow.affects_paper(cfg) is True


# ── observation never touches paper ───────────────────────────────────────────

def test_observe_has_no_paper_parameter():
    params = set(inspect.signature(shadow.observe).parameters)
    assert not any("paper" in p or p == "ps" for p in params)


def test_shadow_module_does_not_import_paper():
    # Structural guard: the observation module never reaches into paper state.
    src = inspect.getsource(shadow)
    assert "packages.paper" not in src
    assert "attempt_open" not in src


def test_observe_uses_injected_builder_and_records_comparison():
    seen = {}

    def fake_builder(symbols, *, risk_action=None):
        seen["symbols"] = symbols
        seen["risk_action"] = risk_action
        return [_view("BTCUSD", action="SCOUT_ALLOWED", direction_score=70, entry_tf="1h", size=0.5)]

    rec = shadow.observe(
        ["BTCUSD"], snapshot_id="snap-9", risk_action="HOLD",
        live_decisions=[_live("BTCUSD", "open_long")],
        cfg=shadow.ShadowConfig(enabled=True, affect_decision=False),
        build_views=fake_builder,
    )
    assert seen == {"symbols": ["BTCUSD"], "risk_action": "HOLD"}
    assert rec["symbols"][0]["agreement"] == "AGREE_ENTRY"
    assert rec["affected_paper"] is False


# ── deterministic agreement labels ────────────────────────────────────────────

def test_agree_entry_same_direction():
    rec = _cmp(
        [_live("BTCUSD", "open_long")],
        [_view("BTCUSD", action="SCOUT_ALLOWED", direction_score=70)],
    )
    assert rec["symbols"][0]["agreement"] == "AGREE_ENTRY"
    assert rec["summary"]["AGREE_ENTRY"] == 1


def test_disagree_direction():
    rec = _cmp(
        [_live("BTCUSD", "open_long")],
        [_view("BTCUSD", action="SCOUT_ALLOWED", direction_score=30)],  # bearish
    )
    assert rec["symbols"][0]["agreement"] == "DISAGREE_DIRECTION"


def test_agree_flat_when_neither_wants_entry():
    rec = _cmp([_live("BTCUSD", "hold")], [_view("BTCUSD", action="NO_TRADE")])
    assert rec["symbols"][0]["agreement"] == "AGREE_FLAT"


def test_shadow_only_entry():
    rec = _cmp([_live("BTCUSD", "hold")], [_view("BTCUSD", action="SCOUT_ALLOWED", direction_score=70)])
    assert rec["symbols"][0]["agreement"] == "SHADOW_ONLY_ENTRY"


def test_live_only_entry():
    rec = _cmp([_live("BTCUSD", "open_long")], [_view("BTCUSD", action="WATCH")])
    assert rec["symbols"][0]["agreement"] == "LIVE_ONLY_ENTRY"


def test_non_actionable_live_entry_counts_as_flat():
    # A live open_* that is not actionable (gated) is NOT a real entry intent.
    rec = _cmp(
        [_live("BTCUSD", "open_long", actionable=False)],
        [_view("BTCUSD", action="NO_TRADE")],
    )
    assert rec["symbols"][0]["live"]["wants_entry"] is False
    assert rec["symbols"][0]["agreement"] == "AGREE_FLAT"


def test_top_live_entry_is_highest_confidence():
    rec = _cmp(
        [
            _live("BTCUSD", "open_long", tf="15m", conf=0.55, size=0.25),
            _live("BTCUSD", "open_long", tf="1h", conf=0.80, size=0.5),
        ],
        [_view("BTCUSD", action="WATCH")],
    )
    live = rec["symbols"][0]["live"]
    assert live["timeframe"] == "1h" and live["confidence"] == 0.80
    assert live["entry_cells"] == 2


# ── tf_weights trust verdict embedding (PRIOR/untrusted visibility) ───────────

_CAL_REPORT = {
    "min_trades_per_tf": 20,
    "tf_weights_prior": {"swing": {"d1": 0.5}},  # dropped by the trim
    "tf_weights_trusted": False,
    "calibrated_timeframes": [],
    "per_timeframe": [
        {"timeframe": "1h", "strategy": "intraday", "trades": 3, "win_rate": 0.33, "trust": "PRIOR", "expectancy": -1.2},
    ],
}


def test_calibration_summary_trims_report():
    s = shadow.calibration_summary(_CAL_REPORT)
    assert s["tf_weights_trusted"] is False
    assert s["min_trades_per_tf"] == 20
    assert s["per_timeframe"][0] == {
        "timeframe": "1h", "strategy": "intraday", "trades": 3, "win_rate": 0.33, "trust": "PRIOR",
    }
    # noisy fields dropped to keep each record lean
    assert "tf_weights_prior" not in s
    assert "expectancy" not in s["per_timeframe"][0]


def test_calibration_summary_empty_on_none():
    assert shadow.calibration_summary(None) == {}
    assert shadow.calibration_summary({}) == {}


def test_build_comparison_embeds_calibration():
    rec = _cmp([_live("BTCUSD", "hold")], [_view("BTCUSD")])
    assert rec["calibration"] == {}  # default when not supplied
    rec2 = shadow.build_comparison(
        snapshot_id="s", risk_action="HOLD",
        live_decisions=[_live("BTCUSD", "hold")], shadow_views=[_view("BTCUSD")],
        cfg=shadow.ShadowConfig(enabled=True, affect_decision=False),
        calibration=shadow.calibration_summary(_CAL_REPORT),
    )
    assert rec2["calibration"]["tf_weights_trusted"] is False
    assert rec2["calibration"]["per_timeframe"][0]["trust"] == "PRIOR"


# ── records are PAPER_SAFE / NO_EXECUTION stamped ─────────────────────────────

def test_record_is_paper_safe_stamped():
    rec = _cmp([_live("BTCUSD", "hold")], [_view("BTCUSD")])
    assert rec["execution_mode"] == "PAPER"
    assert rec["paper_safe"] is True
    assert rec["no_execution"] is True
    assert rec["affected_paper"] is False


def test_record_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    rec = _cmp([_live("BTCUSD", "open_long")], [_view("BTCUSD", action="SCOUT_ALLOWED", direction_score=70)])
    shadow.record(rec)
    back = shadow.read_recent()
    assert len(back) == 1
    assert back[0]["record_id"] == rec["record_id"]
    assert back[0]["affected_paper"] is False
