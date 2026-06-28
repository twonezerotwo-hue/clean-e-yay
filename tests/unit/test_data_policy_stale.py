"""DATA_POLICY — stale OHLCV sert blok (owner-flag, varsayılan KAPALI).

Kapsam:
- `tech_provider.staleness_age_sec`: TF eşiğini aşan bar yaşı döner, taze None.
- `decide_for_symbol`:
  * flag KAPALI (varsayılan) → stale bar AÇILIŞI bloklamaz (mevcut davranış
    korunur; consensus dampening devrede).
  * flag AÇIK + stale bar → action="blocked", blocked_by'da "stale_ohlcv".
  * flag AÇIK + taze bar → stale bloğu YOK.
"""
from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers import technical as tech_provider
from packages.data.types import TechnicalSnapshot


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def _tech(ts: datetime, *, tf: str = "1d") -> TechnicalSnapshot:
    """direction_score taşıyan, OK statülü minimal TechnicalSnapshot."""
    return TechnicalSnapshot(
        symbol="BTCUSD",
        timeframe=tf,
        rsi=60.0,
        macd=0.5,
        atr=100.0,
        ema_stack="bullish",
        score=80.0,
        direction_score=80.0,
        ts=ts,
        status="OK",
        source="test",
        bars_used=400,
    )


# ----------------- helper birim testi -----------------

def test_staleness_age_sec_fresh_returns_none() -> None:
    snap = _tech(datetime.now(UTC), tf="1d")
    assert tech_provider.staleness_age_sec(snap) is None


def test_staleness_age_sec_stale_returns_age() -> None:
    # 1d eşiği 48sa; 10 gün önce → stale.
    old = datetime.now(UTC) - timedelta(days=10)
    age = tech_provider.staleness_age_sec(_tech(old, tf="1d"))
    assert age is not None and age > 172800


def test_staleness_age_sec_no_bars_returns_none() -> None:
    snap = _tech(datetime.now(UTC), tf="1d")
    snap.bars_used = 0
    assert tech_provider.staleness_age_sec(snap) is None


# ----------------- decision gate testleri -----------------

def _setup(monkeypatch, *, ts: datetime, flag: bool):
    """Güçlü bullish consensus + verilen tazelikte teknik snapshot + flag."""
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.data.registry import loader
    from packages.decision import engine as dec
    from packages.regime.classifier import classify

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    # Karar TF'inin teknik snapshot'ını kontrollü tazelikle enjekte et.
    snap.technicals_by_tf = {"BTCUSD": {"1d": _tech(ts, tf="1d")}}

    fake = ConsensusResult(
        symbol="BTCUSD",
        score=85.0,
        direction="bullish",
        confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=85.0, weight=1.0, contribution=85.0)],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)

    real = loader.load_thresholds()

    def fake_load():
        d = dict(real)
        d["data_policy"] = {"block_stale_ohlcv_for_trade": flag}
        return d

    monkeypatch.setattr(dec, "load_thresholds", fake_load)
    return dec, snap, regime


def test_flag_off_stale_does_not_block(fresh_env, monkeypatch) -> None:
    from packages.risk.engine import RiskDecision

    old = datetime.now(UTC) - timedelta(days=10)
    dec, snap, regime = _setup(monkeypatch, ts=old, flag=False)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])

    d = dec.decide_for_symbol("BTCUSD", snap, regime, hold_risk, timeframe="1d")
    assert "stale_ohlcv" not in " ".join(d.blocked_by)


def test_flag_on_stale_blocks(fresh_env, monkeypatch) -> None:
    from packages.risk.engine import RiskDecision

    old = datetime.now(UTC) - timedelta(days=10)
    dec, snap, regime = _setup(monkeypatch, ts=old, flag=True)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])

    d = dec.decide_for_symbol("BTCUSD", snap, regime, hold_risk, timeframe="1d")
    assert d.action == "blocked"
    assert any(b.startswith("stale_ohlcv:") for b in d.blocked_by)
    assert d.size_multiplier == 0.0


def test_flag_on_fresh_does_not_block(fresh_env, monkeypatch) -> None:
    from packages.risk.engine import RiskDecision

    fresh = datetime.now(UTC)
    dec, snap, regime = _setup(monkeypatch, ts=fresh, flag=True)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])

    d = dec.decide_for_symbol("BTCUSD", snap, regime, hold_risk, timeframe="1d")
    assert "stale_ohlcv" not in " ".join(d.blocked_by)
