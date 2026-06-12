"""v2.7 D4 — Realized Volatility / Volatility Regime Intelligence testleri.

Hepsi offline (live network yok). Doğrulanan invariant'lar:

- Realized vol fixture OHLCV barlarından deterministik hesaplanır.
- Yetersiz bar → DEGRADED (insufficient_bars), crash yok, mock yok.
- z-score → rejim (LOW/NORMAL/ELEVATED/EXTREME); squeeze/expansion/shock bayrağı.
- Gate yalnızca KISITLAYICI: EXTREME → NO_POSITION_INCREASE (block);
  ELEVATED → CAUTION ×0.5; LOW + squeeze → WATCH (yalnızca bağlam, boost YOK).
- Gate ASLA size artırmaz (size_factor ≤ 1.0).
- Timeframe ağırlığı: 1w → etki yok; düşük ağırlık (1d) block'u CAUTION'a yumuşatır.
- Doğrulanmamış (fixture) snapshot karar zincirine GİRMEZ; yalnızca bağlam.
- decide_matrix: verified EXTREME → hücre blocked_by ile durur; DQS BLOCKED /
  KILL_SWITCH her zaman finaldir (volatilite bypass etmez).
"""
from __future__ import annotations

import importlib
import math
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers import volatility as vol_provider
from packages.data.providers.volatility import engine as vol_engine
from packages.data.types import OHLCVBar, TechnicalSnapshot, VolatilitySnapshot
from packages.risk import volatility_risk
from packages.risk.engine import RiskInput

_STEP = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _bars_from_returns(rets: list[float], tf: str = "1h", start: float = 100.0) -> list[OHLCVBar]:
    closes = [start]
    for r in rets:
        closes.append(closes[-1] * math.exp(r))
    step = _STEP[tf]
    # Son bar şimdiye yakın olsun (freshness FRESH) — t0'ı geriye doğru kur.
    t0 = _NOW - step * (len(closes) - 1)
    return [
        OHLCVBar(
            symbol="BTCUSD", timeframe=tf, ts=t0 + step * i,  # type: ignore[arg-type]
            open=c, high=c, low=c, close=c, source="test", verified=True,
        )
        for i, c in enumerate(closes)
    ]


def _vin(rets: list[float], tf: str = "1h") -> vol_engine.VolInput:
    return vol_engine.VolInput(
        symbol="BTCUSD", timeframe=tf, bars=_bars_from_returns(rets, tf),
        source="test", verified=True,
    )


# ---------------- engine: hesap + DEGRADED ----------------

def test_insufficient_bars_is_degraded() -> None:
    snap = vol_engine.compute(_vin([0.01] * 5), now=_NOW)
    assert snap.status == "DEGRADED"
    assert snap.error == "insufficient_bars"
    assert snap.realized_vol is None


def test_compute_ok_fields_present() -> None:
    # 80 sıradan getiri → OK; tüm alanlar dolu.
    rets = [0.01 if i % 2 == 0 else -0.01 for i in range(80)]
    snap = vol_engine.compute(_vin(rets), now=_NOW)
    assert snap.status == "OK"
    assert snap.realized_vol is not None and snap.realized_vol > 0
    assert snap.rv_short is not None and snap.rv_long is not None
    assert snap.vol_zscore is not None
    assert snap.regime in ("LOW", "NORMAL", "ELEVATED", "EXTREME")
    assert snap.bars_used == 81


def test_compute_is_deterministic() -> None:
    rets = [0.005 * ((-1) ** i) for i in range(90)]
    a = vol_engine.compute(_vin(rets), now=_NOW)
    b = vol_engine.compute(_vin(rets), now=_NOW)
    assert a.realized_vol == b.realized_vol
    assert a.vol_zscore == b.vol_zscore
    assert a.regime == b.regime


def test_recent_vol_burst_is_extreme_regime() -> None:
    # Sakin baseline (60) + son 20 barda patlama → z yüksek → ELEVATED/EXTREME.
    calm = [0.0005 * ((-1) ** i) for i in range(60)]
    burst = [0.06 * ((-1) ** i) for i in range(20)]
    snap = vol_engine.compute(_vin(calm + burst), now=_NOW)
    assert snap.status == "OK"
    assert snap.regime in ("ELEVATED", "EXTREME")
    assert snap.vol_zscore is not None and snap.vol_zscore > 1.0
    # rv_short >> rv_long → genişleme/şok bağlamı (normal değil).
    assert snap.vol_state in ("expansion", "shock")


def test_squeeze_when_recent_vol_collapses() -> None:
    # Hareketli baseline + son barlarda sönüm → rv_short/rv_long düşük → squeeze.
    loud = [0.03 * ((-1) ** i) for i in range(60)]
    quiet = [0.0008 * ((-1) ** i) for i in range(20)]
    snap = vol_engine.compute(_vin(loud + quiet), now=_NOW)
    assert snap.status == "OK"
    assert snap.vol_state == "squeeze"


def test_shock_when_last_bar_jumps() -> None:
    rets = [0.003 * ((-1) ** i) for i in range(79)] + [0.25]  # tek dev son getiri
    snap = vol_engine.compute(_vin(rets), now=_NOW)
    assert snap.status == "OK"
    assert snap.vol_state == "shock"


# ---------------- orchestrator: cache, DEGRADED, ağsız ----------------

def test_get_volatility_returns_symbol_tf_grid() -> None:
    out = vol_provider.get_volatility(["BTCUSD"], ["1h", "1d"])
    assert set(out.keys()) == {"BTCUSD"}
    assert set(out["BTCUSD"].keys()) == {"1h", "1d"}


def test_fixture_mode_snapshot_is_unverified() -> None:
    # conftest TEST_USE_MOCK=true → fixture barlar; verified=False (karar dışı).
    out = vol_provider.get_volatility(["BTCUSD"], ["1d"])
    snap = out["BTCUSD"]["1d"]
    assert snap.verified is False  # fixture asla karar zincirine girmez


def test_orchestrator_degraded_when_no_bars(monkeypatch) -> None:
    monkeypatch.setattr(vol_provider.ohlcv_provider, "get_bars", lambda s, tf: [])
    vol_provider.reset_provider_status()
    out = vol_provider.get_volatility(["BTCUSD"], ["1h"])
    snap = out["BTCUSD"]["1h"]
    assert snap.status == "DEGRADED"
    assert snap.verified is False
    assert vol_provider.get_provider_status()["volatility"]["status"] == "degraded"


def test_get_volatility_makes_no_network_call(monkeypatch) -> None:
    def _boom(*_a, **_k):  # pragma: no cover - çağrılmamalı
        raise AssertionError("volatility fixture modunda ağa çıkmamalı")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    out = vol_provider.get_volatility(["BTCUSD"], ["1h"])
    assert out["BTCUSD"]["1h"].symbol == "BTCUSD"


# ---------------- gate: yalnızca kısıtlayıcı ----------------

def _snap(
    *,
    regime: str = "NORMAL",
    vol_state: str = "normal",
    verified: bool = True,
    status: str = "OK",
    z: float | None = 0.0,
    rv: float | None = 0.4,
    tf: str = "1h",
) -> VolatilitySnapshot:
    return VolatilitySnapshot(
        symbol="BTCUSD",
        timeframe=tf,  # type: ignore[arg-type]
        realized_vol=rv,
        rv_short=rv,
        rv_long=rv,
        vol_zscore=z,
        regime=regime,    # type: ignore[arg-type]
        vol_state=vol_state,  # type: ignore[arg-type]
        status=status,    # type: ignore[arg-type]
        source="test",
        verified=verified,
        evidence=["test"],
    )


def test_gate_none_when_no_data() -> None:
    assert volatility_risk.assess(None, "open_long").level == "NONE"


def test_gate_ignores_unverified_snapshot() -> None:
    v = volatility_risk.assess(_snap(regime="EXTREME", verified=False), "open_long")
    assert v.level == "NONE"  # fixture/test verisi karar zincirine girmez


def test_gate_ignores_degraded_snapshot() -> None:
    v = volatility_risk.assess(_snap(regime="EXTREME", status="DEGRADED"), "open_long")
    assert v.level == "NONE"


def test_gate_extreme_regime_blocks_position_increase() -> None:
    v = volatility_risk.assess(_snap(regime="EXTREME", z=2.5), "open_long")
    assert v.level == "NO_POSITION_INCREASE"
    assert v.block is True
    assert v.size_factor == 0.0


def test_gate_elevated_regime_is_caution_half_size() -> None:
    v = volatility_risk.assess(_snap(regime="ELEVATED", z=1.4), "open_long")
    assert v.level == "CAUTION"
    assert v.block is False
    assert v.size_factor == 0.5


def test_gate_low_vol_squeeze_is_context_only_no_boost() -> None:
    # LOW rejim + squeeze breakout → yalnızca WATCH bağlamı; ASLA boost.
    v = volatility_risk.assess(_snap(regime="LOW", vol_state="squeeze", z=-1.5), "open_long")
    assert v.level == "WATCH"
    assert v.size_factor == 1.0  # asla artmaz, asla azalmaz (yalnızca bağlam)
    assert v.block is False


def test_gate_shock_on_normal_regime_is_caution() -> None:
    v = volatility_risk.assess(_snap(regime="NORMAL", vol_state="shock"), "open_long")
    assert v.level == "CAUTION"


def test_gate_shock_on_elevated_regime_blocks() -> None:
    v = volatility_risk.assess(_snap(regime="ELEVATED", vol_state="shock"), "open_long")
    assert v.level == "NO_POSITION_INCREASE"
    assert v.block is True


def test_gate_never_boosts_size() -> None:
    for regime in ("LOW", "NORMAL", "ELEVATED", "EXTREME"):
        for state in ("normal", "squeeze", "expansion", "shock"):
            v = volatility_risk.assess(_snap(regime=regime, vol_state=state), "open_long")
            assert v.size_factor <= 1.0


# ---------------- gate: timeframe ağırlığı ----------------

def test_timeframe_weight_weekly_is_zero() -> None:
    assert volatility_risk.timeframe_weight("1w") == 0.0
    assert volatility_risk.timeframe_weight("1h") == 1.0


def test_apply_timeframe_softens_block_on_low_weight() -> None:
    extreme = volatility_risk.assess(_snap(regime="EXTREME", z=2.5), "open_long")
    # 1d ağırlığı (0.5) < block eşiği (0.75) → block CAUTION'a yumuşar (rejim bağlamı).
    softened = volatility_risk.apply_timeframe(extreme, volatility_risk.timeframe_weight("1d"))
    assert softened.block is False
    assert softened.level == "CAUTION"
    assert softened.size_factor <= 1.0


def test_apply_timeframe_full_weight_keeps_block() -> None:
    extreme = volatility_risk.assess(_snap(regime="EXTREME", z=2.5), "open_long")
    kept = volatility_risk.apply_timeframe(extreme, 1.0)
    assert kept.block is True
    assert kept.level == "NO_POSITION_INCREASE"


def test_apply_timeframe_zero_weight_disables_effect() -> None:
    extreme = volatility_risk.assess(_snap(regime="EXTREME", z=2.5), "open_long")
    off = volatility_risk.apply_timeframe(extreme, 0.0)
    assert off.level == "NONE"
    assert off.block is False


# ---------------- decide_matrix entegrasyonu (uçtan uca) ----------------


def _risk_in(dqs: float = 90.0, daily_pnl: float = 0.0) -> RiskInput:
    return RiskInput(
        dqs_score=dqs,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=daily_pnl,
        open_position_count=0,
    )


@pytest.fixture
def paper_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    from packages.paper import state as ps_mod
    importlib.reload(ps_mod)
    return ps_mod


def _force_bullish(snap, symbol: str = "BTCUSD") -> None:
    for tf in ("15m", "1h", "4h", "1d", "1w"):
        snap.technicals_by_tf[symbol][tf] = TechnicalSnapshot(
            symbol=symbol, timeframe=tf, rsi=85.0, macd=2.0, atr=1.0,
            ema_stack="bullish", score=95.0, status="OK",
        )
    snap.technicals[symbol] = snap.technicals_by_tf[symbol]["1d"]


def test_matrix_extreme_vol_blocks_open_cell(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.volatility["BTCUSD"]["1h"] = _snap(regime="EXTREME", z=2.6, verified=True)
    regime, risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["1h"])
    d = decisions[0]
    assert d.action == "hold"  # NO_POSITION_INCREASE → açılış durdu
    assert any(b.startswith("volatility_risk:") for b in d.blocked_by)
    assert d.volatility_report.get("regime") == "EXTREME"

    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"], timeframes=["1h"])
    assert any(s["symbol"] == "BTCUSD" for s in view["volatility"])
    assert any(
        b.startswith("volatility_risk:") for c in view["cells"] for b in c["blocked_by"]
    )


def test_matrix_elevated_vol_reduces_size_but_keeps_open(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    base = build_snapshot(["BTCUSD"])
    _force_bullish(base)
    base.volatility.clear()  # vol etkisi yok → baseline size
    _r, _k, base_dec = decide_matrix(["BTCUSD"], base, _risk_in(), timeframes=["1h"])

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.volatility["BTCUSD"]["1h"] = _snap(regime="ELEVATED", z=1.5, verified=True)
    _r, _k, dec = decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["1h"])

    assert base_dec[0].action == "open_long"
    assert dec[0].action == "open_long"  # açılış korunur
    assert dec[0].volatility_report.get("level") == "CAUTION"
    assert dec[0].size_multiplier < base_dec[0].size_multiplier  # küçüldü, artmadı


def test_matrix_unverified_vol_does_not_block_open(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.volatility["BTCUSD"]["1h"] = _snap(regime="EXTREME", z=2.6, verified=False)
    _r, _k, decisions = decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["1h"])
    assert decisions[0].action == "open_long"  # unverified → bloklamadı
    assert not any(
        b.startswith("volatility_risk:") for d in decisions for b in d.blocked_by
    )


def test_matrix_dqs_blocked_overrides_volatility(paper_env) -> None:
    # DQS BLOCKED → tüm hücreler SUSPENDED; volatilite gate'i bypass edemez.
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.volatility["BTCUSD"]["1h"] = _snap(regime="EXTREME", z=2.6, verified=True)
    regime, risk, decisions = decide_matrix(
        ["BTCUSD"], snap, _risk_in(dqs=40.0), timeframes=["1h"]
    )
    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"], timeframes=["1h"])
    assert view["suspended"] is True
    assert decisions[0].action != "open_long"


def test_matrix_kill_switch_overrides_volatility(paper_env) -> None:
    # KILL_SWITCH (günlük zarar) her zaman final; volatilite bypass etmez.
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.volatility["BTCUSD"]["1h"] = _snap(regime="LOW", vol_state="squeeze", verified=True)
    _r, risk, decisions = decide_matrix(
        ["BTCUSD"], snap, _risk_in(daily_pnl=-9000.0), timeframes=["1h"]
    )
    assert risk.action == "KILL_SWITCH"
    d = decisions[0]
    assert d.action == "blocked"
    assert any(b.startswith("risk_gate:") for b in d.blocked_by)
