"""Concentration guard (shadow-first) — aynı-sembol aynı-yön yığın sınırı testleri.

Kök neden: DODO 1h+4h gibi TEK sinyalin TF'lere kopyalanması tek market olayına 2x
maruz kalmaktır (canlıda −692 kayıp). G4 correlation cluster equity'nin %30'unda
tetikler → DODO 2 leg = equity'nin %9'u, G4 hiç görmedi. Bu guard tek-sembol yığınına
sıkı sınır koyar.

- Pür değerlendirici (`_concentration_report`): leg-sayısı VE exposure-oranı breach.
- Aktif guard: flag KAPALI iken aday geçer (yalnız gözlem, active=False);
  flag AÇIK + breach iken aynı-yön yeni leg bloklanır.
- Kill-override (CP3 kasa): guard_overrides.is_disabled → enabled zorla False.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("GUARD_OVERRIDES_PATH", str(tmp_path / "guard_overrides.json"))
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


# ---------------- pür değerlendirici ----------------

def test_report_empty_when_no_same_side_leg(fresh_env) -> None:
    from packages.decision import engine as dec
    cfg = {"enabled": True, "max_same_dir_legs": 1, "max_symbol_pct": 0.05}
    # aynı sembolde yalnız ZIT yön açık → aynı-yön yığın yok → boş rapor
    short = _pos(fresh_env, symbol="DODO", side="short", size_usd=4_500, timeframe="1h")
    rep = dec._concentration_report("DODO", "long", [short], 99_000, cfg)
    assert rep == {}


def test_report_breach_on_leg_count(fresh_env) -> None:
    from packages.decision import engine as dec
    cfg = {"enabled": True, "max_same_dir_legs": 1, "max_symbol_pct": 0.99}
    long1 = _pos(fresh_env, symbol="DODO", side="long", size_usd=3_800, timeframe="1h")
    rep = dec._concentration_report("DODO", "long", [long1], 99_000, cfg)
    assert rep["breach"] is True
    assert rep["breach_reason"] == "leg_count"
    assert rep["open_same_dir_count"] == 1
    assert rep["timeframes"] == ["1h"]


def test_report_breach_on_exposure_pct(fresh_env) -> None:
    from packages.decision import engine as dec
    # leg-sayısı yüksek eşik (breach etmez) ama exposure %5 eşiğini aşar
    cfg = {"enabled": True, "max_same_dir_legs": 9, "max_symbol_pct": 0.05}
    long1 = _pos(fresh_env, symbol="DODO", side="long", size_usd=6_000, timeframe="1h")
    rep = dec._concentration_report("DODO", "long", [long1], 99_000, cfg)
    assert rep["breach"] is True
    assert rep["breach_reason"] == "exposure_pct"
    assert rep["exposure_pct"] == pytest.approx(0.0606, abs=1e-3)


def test_report_no_breach_under_thresholds(fresh_env) -> None:
    from packages.decision import engine as dec
    cfg = {"enabled": True, "max_same_dir_legs": 3, "max_symbol_pct": 0.20}
    long1 = _pos(fresh_env, symbol="DODO", side="long", size_usd=3_800, timeframe="1h")
    rep = dec._concentration_report("DODO", "long", [long1], 99_000, cfg)
    assert rep["breach"] is False
    assert rep["active"] is True


# ---------------- config seam + kill-override ----------------

def test_cfg_forced_off_by_kill_override(fresh_env, monkeypatch) -> None:
    from packages.data.registry import guard_overrides
    from packages.decision import engine as dec
    importlib.reload(guard_overrides)
    monkeypatch.setattr(
        dec, "load_thresholds",
        lambda: {"book_audit": {"concentration_guard": {"enabled": True, "max_same_dir_legs": 1}}},
    )
    # kasa kill-override yazmadan → enabled True
    assert dec._concentration_cfg().get("enabled") is True
    # kasa concentration'ı kapattı → enabled zorla False (config'e dokunmadan)
    guard_overrides.set_disabled("concentration", reason="test")
    assert dec._concentration_cfg().get("enabled") is False


# ---------------- aktif guard (end-to-end) ----------------

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


def test_guard_off_allows_but_observes(fresh_env, monkeypatch) -> None:
    dec, snap, regime = _force_pass(monkeypatch)
    from packages.risk.engine import RiskDecision
    monkeypatch.setattr(dec, "_concentration_cfg", lambda: {"enabled": False, "max_same_dir_legs": 1})
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    # aynı sembolde zaten AYNI yön (long) açık — flag KAPALI → aday yine de geçer
    long_pos = _pos(fresh_env, symbol="BTCUSD", side="long", size_usd=5_000, timeframe="4h")
    d = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk, open_positions=[long_pos], equity_usd=100_000
    )
    assert d.action == "open_long"  # davranış değişmez
    assert d.concentration_report.get("active") is False
    assert d.concentration_report.get("open_same_dir_count") == 1


def test_guard_on_blocks_same_dir_stack(fresh_env, monkeypatch) -> None:
    dec, snap, regime = _force_pass(monkeypatch)
    from packages.risk.engine import RiskDecision
    monkeypatch.setattr(
        dec, "_concentration_cfg",
        lambda: {"enabled": True, "max_same_dir_legs": 1, "max_symbol_pct": 0.05},
    )
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    long_pos = _pos(fresh_env, symbol="BTCUSD", side="long", size_usd=5_000, timeframe="4h")
    d = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk, open_positions=[long_pos], equity_usd=100_000
    )
    assert d.action == "hold"
    assert "concentration_guard" in d.blocked_by
    assert d.concentration_report.get("active") is True
    assert d.concentration_report.get("breach") is True


def test_guard_on_allows_first_leg(fresh_env, monkeypatch) -> None:
    """Aynı sembolde açık AYNI yön leg yoksa (ilk giriş) guard tetiklenmez."""
    dec, snap, regime = _force_pass(monkeypatch)
    from packages.risk.engine import RiskDecision
    monkeypatch.setattr(
        dec, "_concentration_cfg",
        lambda: {"enabled": True, "max_same_dir_legs": 1, "max_symbol_pct": 0.05},
    )
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    # farklı sembolde açık pozisyon → BTCUSD ilk leg → geçer
    other = _pos(fresh_env, symbol="ETHUSD", side="long", size_usd=5_000, timeframe="4h")
    d = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk, open_positions=[other], equity_usd=100_000
    )
    assert d.action == "open_long"
    assert d.concentration_report == {}
