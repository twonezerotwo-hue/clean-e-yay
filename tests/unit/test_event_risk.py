"""P0 — Olay riski (event risk) testleri.

Hepsi offline (live network yok). Doğrulanan invariant'lar:

- Yüksek etkili + yakın doğrulanmış olay → NO_POSITION_INCREASE (kısıtlayıcı).
- Düşük etkili / uzak olay → hard block YOK.
- verified=False olay (fixture/test) → karar zincirine GİRMEZ.
- Event riski RiskGate'i BYPASS ETMEZ: DQS BLOCKED / halt KILL_SWITCH her
  zaman ezer; event riski hiçbir gate'i gevşetemez, size artıramaz.
- Sağlayıcı verisi yoksa (boş catalyst) → crash yok, NONE.
"""
from __future__ import annotations

import urllib.request
from datetime import timedelta

import pytest

from packages.data.types import Catalyst, utcnow
from packages.risk import event_risk
from packages.risk.engine import RiskInput
from packages.risk.engine import evaluate as evaluate_risk


def _cat(
    title: str,
    importance: str,
    hours: float,
    *,
    verified: bool = True,
    cid: str | None = None,
) -> Catalyst:
    now = utcnow()
    ts = now + timedelta(hours=hours)
    return Catalyst(
        id=cid or f"{title}|{hours}",
        ts=ts,
        title=title,
        importance=importance,  # type: ignore[arg-type]
        days_until=int(hours // 24),
        hours_until=round(hours, 1),
        source="event_calendar.yaml",
        verified=verified,
    )


# ---------------- assess: seviye taksonomisi ----------------

def test_high_impact_near_blocks_position_increase() -> None:
    res = event_risk.assess([_cat("US CPI", "critical", 5)])
    assert res.level == "NO_POSITION_INCREASE"
    assert res.action == "NO_POSITION_INCREASE"
    assert res.restrictive is True
    assert res.triggers and res.triggers[0].title == "US CPI"


def test_high_impact_mid_window_is_watch_only() -> None:
    # 48h: block penceresinin (24h) dışında ama watch (72h) içinde → WATCH
    res = event_risk.assess([_cat("FOMC", "high", 48)])
    assert res.level == "WATCH"
    assert res.action == "WATCH"
    assert res.restrictive is False  # yeni pozisyonu bloklamaz


def test_medium_impact_near_is_watch_not_block() -> None:
    res = event_risk.assess([_cat("ECB Speech", "medium", 5)])
    assert res.level == "WATCH"
    assert res.restrictive is False


def test_low_impact_event_no_hard_block() -> None:
    res = event_risk.assess([_cat("Jobless Claims", "low", 3)])
    assert res.level == "NONE"
    assert res.action is None
    assert res.restrictive is False


def test_far_high_impact_event_no_effect() -> None:
    res = event_risk.assess([_cat("Jackson Hole", "critical", 200)])
    assert res.level == "NONE"


def test_unverified_event_ignored() -> None:
    # Fixture/test event'leri verified=False → karar zincirine girmez.
    res = event_risk.assess([_cat("US CPI", "critical", 4, verified=False)])
    assert res.level == "NONE"
    assert not res.triggers


def test_most_restrictive_trigger_wins() -> None:
    res = event_risk.assess(
        [
            _cat("Far FOMC", "high", 60),       # WATCH
            _cat("Imminent CPI", "critical", 3),  # NO_POSITION_INCREASE
        ]
    )
    assert res.level == "NO_POSITION_INCREASE"
    # Tüm tetikleyiciler görünür (dashboard için), en kısıtlayıcı başta.
    assert {t.title for t in res.triggers} == {"Far FOMC", "Imminent CPI"}
    assert res.triggers[0].level == "NO_POSITION_INCREASE"


# ---------------- RiskGate entegrasyonu (bypass yok) ----------------

def _clean_risk_in(dqs: float = 90.0) -> RiskInput:
    return RiskInput(
        dqs_score=dqs,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=0,
        open_position_count=0,
    )


def test_event_risk_tightens_open_gate() -> None:
    cands = event_risk.risk_candidates([_cat("US CPI", "critical", 4)])
    assert cands and cands[0][0] == "NO_POSITION_INCREASE"
    decision = evaluate_risk(_clean_risk_in(), event_candidates=cands)
    assert decision.action == "NO_POSITION_INCREASE"


def test_event_risk_never_loosens_killswitch_from_dqs() -> None:
    # DQS BLOCKED → KILL_SWITCH; event riski (NO_POSITION_INCREASE) ezemez.
    cands = event_risk.risk_candidates([_cat("US CPI", "critical", 4)])
    decision = evaluate_risk(_clean_risk_in(dqs=40.0), event_candidates=cands)
    assert decision.action == "KILL_SWITCH"


def test_event_risk_does_not_bypass_daily_loss_halt() -> None:
    # Günlük zarar limiti aşılmış → KILL_SWITCH; event riski yine ezemez.
    cands = event_risk.risk_candidates([_cat("US CPI", "critical", 4)])
    breached = RiskInput(
        dqs_score=90.0,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=-5_000,  # %2 limitin çok altında
        open_position_count=0,
    )
    decision = evaluate_risk(breached, event_candidates=cands)
    assert decision.action == "KILL_SWITCH"


def test_event_risk_candidate_action_is_only_restrictive() -> None:
    # Event riski yalnızca WATCH veya NO_POSITION_INCREASE üretebilir —
    # asla RISK_REDUCE/KILL_SWITCH (yani gate'i sertleştirip trade'i tümden
    # kesemez, sadece pozisyon artışını durdurur) ve asla HEDGE/HOLD'u gevşetmez.
    for imp, hours in [("critical", 3), ("high", 3), ("high", 48), ("medium", 3)]:
        cands = event_risk.risk_candidates([_cat("X", imp, hours)])
        for action, _reason, _ev in cands:
            assert action in {"WATCH", "NO_POSITION_INCREASE"}


# ---------------- sağlamlık ----------------

def test_no_catalysts_no_crash_none() -> None:
    assert event_risk.assess([]).level == "NONE"
    assert event_risk.risk_candidates([]) == []


def test_assess_makes_no_network_call(monkeypatch) -> None:
    def _boom(*_a, **_k):  # pragma: no cover - çağrılmamalı
        raise AssertionError("event_risk live network'e çıkmamalı")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    res = event_risk.assess([_cat("US CPI", "critical", 4)])
    assert res.restrictive is True


def test_now_override_recomputes_window() -> None:
    # ts sabit; `now` ileri alınınca olay uzaklaşır → NONE.
    cat = _cat("US CPI", "critical", 4)
    far_future = cat.ts + timedelta(hours=100)
    res = event_risk.assess([cat], now=far_future)
    assert res.level == "NONE"


# ---------------- decide_matrix entegrasyonu (uçtan uca) ----------------

def _risk_in(dqs: float = 90.0) -> RiskInput:
    return RiskInput(
        dqs_score=dqs,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=0,
        open_position_count=0,
    )


def test_matrix_suspends_on_high_impact_event() -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    snap.catalysts = [_cat("US CPI", "critical", 4)]
    regime, risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    assert risk.action == "NO_POSITION_INCREASE"
    assert all(d.action in {"hold", "blocked"} for d in decisions)

    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"])
    assert view["suspended"] is True
    assert view["event_risk"]["level"] == "NO_POSITION_INCREASE"
    assert view["event_risk"]["restrictive"] is True
    assert all(c["status"] == "SUSPENDED" for c in view["cells"])


def test_matrix_event_risk_visible_but_dqs_block_final() -> None:
    # DQS BLOCKED → KILL_SWITCH final; event riski yine de görünür (bağlam).
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    snap.catalysts = [_cat("US CPI", "critical", 4)]
    regime, risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in(dqs=40.0))
    assert risk.action == "KILL_SWITCH"  # event riski ezemedi
    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"])
    assert view["event_risk"]["level"] == "NO_POSITION_INCREASE"  # bağlam görünür
    assert all(c["status"] == "SUSPENDED" for c in view["cells"])


def test_matrix_no_event_means_no_event_suspension() -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    snap.catalysts = [_cat("Far Jackson Hole", "critical", 300)]  # etki yok
    regime, risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"])
    assert view["event_risk"]["level"] == "NONE"
    assert risk.action != "NO_POSITION_INCREASE"
