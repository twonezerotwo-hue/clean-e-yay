"""v2.7 D3 — Options IV / Skew / Term Structure Intelligence testleri.

Hepsi offline (live network yok). Doğrulanan invariant'lar:

- Fixture options chain parse; ATM IV / 25Δ skew proxy / put-call OI /
  IV-RV spread / term structure deterministik hesaplanır.
- skew_25d GERÇEK greeks değil (is_proxy=True; moneyness proxy).
- Stres rejimi sınıflandırma (RICH_VOL / CHEAP_VOL / PUT_SKEW_STRESS /
  CALL_SKEW_EUPHORIA / TERM_STRESS / NORMAL).
- Deribit adapter instrument_name parse; başarısız → None (mock yok, crash yok).
- Sağlayıcı başarısız → DEGRADED snapshot; chain boş → UNAVAILABLE.
- Gate yalnızca KISITLAYICI: PUT_SKEW/CALL_SKEW + long → CAUTION; TERM_STRESS →
  NO_POSITION_INCREASE; RICH_VOL → CAUTION; CHEAP_VOL → WATCH (boost YOK).
- Gate ASLA size artırmaz (size_factor ≤ 1.0).
- Timeframe ağırlığı: options 1d/1w tam, 15m düşük; düşük ağırlık block'u yumuşatır.
- Yalnızca BTC/ETH işlenir; doğrulanmamış (fixture) snapshot karar dışı.
- decide_matrix entegrasyonu: verified TERM_STRESS → hücre durur; DQS BLOCKED →
  options değil risk_gate kıstırır (bypass yok); unverified → bloklamaz.
"""
from __future__ import annotations

import importlib
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers import options as options_provider
from packages.data.providers.options import deribit
from packages.data.providers.options import engine as opt_engine
from packages.data.types import OptionsSnapshot, TechnicalSnapshot
from packages.risk import options_risk
from packages.risk.engine import RiskInput

_REF = datetime(2026, 6, 13, 12, tzinfo=UTC)
_FRONT = _REF + timedelta(days=7)
_NEXT = _REF + timedelta(days=35)
_LONG = _REF + timedelta(days=90)


def _q(expiry, strike, otype, iv, oi=100.0):
    return opt_engine.OptionQuote(
        expiry_ts=expiry,
        strike=strike,
        option_type=otype,
        mark_iv=iv,
        open_interest=oi,
        expiry_label=expiry.date().isoformat(),
    )


def _chain(
    *,
    underlying=100.0,
    atm_iv=0.50,
    otm_call_iv=None,
    otm_put_iv=None,
    long_atm_iv=None,
    realized=None,
    put_oi=100.0,
    call_oi=100.0,
) -> opt_engine.OptionsInput:
    otm_call_iv = atm_iv if otm_call_iv is None else otm_call_iv
    otm_put_iv = atm_iv if otm_put_iv is None else otm_put_iv
    quotes = [
        _q(_FRONT, underlying, "call", atm_iv, call_oi),
        _q(_FRONT, underlying, "put", atm_iv, put_oi),
        _q(_FRONT, underlying * 1.10, "call", otm_call_iv, call_oi),
        _q(_FRONT, underlying * 0.90, "put", otm_put_iv, put_oi),
    ]
    if long_atm_iv is not None:
        quotes += [
            _q(_LONG, underlying, "call", long_atm_iv, call_oi),
            _q(_LONG, underlying, "put", long_atm_iv, put_oi),
        ]
    return opt_engine.OptionsInput(
        symbol="BTCUSD",
        underlying_price=underlying,
        quotes=quotes,
        realized_vol=realized,
        source="test",
        verified=True,
        ts=_REF,
    )


# ---------------- engine: parse + metrikler ----------------

def test_compute_ok_computes_core_metrics() -> None:
    snap = opt_engine.compute(
        _chain(atm_iv=0.55, otm_call_iv=0.52, otm_put_iv=0.58, long_atm_iv=0.54, realized=0.45),
        now=_REF,
    )
    assert snap.status == "OK"
    assert snap.is_proxy is True
    assert snap.atm_iv == 0.55
    # skew proxy = call_iv − put_iv = 0.52 − 0.58 = −0.06 (put skew).
    assert snap.skew_25d == pytest.approx(-0.06)
    # IV−RV spread = 0.55 − 0.45 = 0.10.
    assert snap.iv_rv_spread == pytest.approx(0.10)
    # term slope = long − front = 0.54 − 0.55 = −0.01.
    assert snap.term_slope == pytest.approx(-0.01)
    assert snap.evidence


def test_put_call_oi_ratio() -> None:
    snap = opt_engine.compute(_chain(put_oi=300.0, call_oi=100.0), now=_REF)
    # put OI = 2×300=600 (ATM + OTM put), call OI = 2×100=200 → 3.0.
    assert snap.put_call_oi_ratio == pytest.approx(3.0)


def test_compute_unavailable_when_no_chain() -> None:
    inp = opt_engine.OptionsInput(symbol="BTCUSD", underlying_price=100.0, quotes=[], ts=_REF)
    snap = opt_engine.compute(inp, now=_REF)
    assert snap.status == "UNAVAILABLE"
    assert snap.error


def test_compute_degraded_when_no_underlying() -> None:
    inp = opt_engine.OptionsInput(
        symbol="BTCUSD", underlying_price=None, quotes=[_q(_FRONT, 100, "call", 0.5)], ts=_REF
    )
    snap = opt_engine.compute(inp, now=_REF)
    assert snap.status == "UNAVAILABLE"  # underlying yok → karar dışı


def test_compute_is_deterministic() -> None:
    a = opt_engine.compute(_chain(realized=0.4), now=_REF)
    b = opt_engine.compute(_chain(realized=0.4), now=_REF)
    assert a.atm_iv == b.atm_iv and a.skew_25d == b.skew_25d and a.regime == b.regime


# ---------------- engine: rejim sınıflandırma ----------------

def test_regime_rich_vol() -> None:
    snap = opt_engine.compute(_chain(atm_iv=0.60, realized=0.45), now=_REF)  # spread +0.15
    assert snap.regime == "RICH_VOL"


def test_regime_cheap_vol() -> None:
    snap = opt_engine.compute(_chain(atm_iv=0.40, realized=0.55), now=_REF)  # spread −0.15
    assert snap.regime == "CHEAP_VOL"


def test_regime_put_skew_stress() -> None:
    # skew = 0.50 − 0.56 = −0.06 ≤ −0.03; term/iv-rv nötr.
    snap = opt_engine.compute(_chain(otm_call_iv=0.50, otm_put_iv=0.56), now=_REF)
    assert snap.regime == "PUT_SKEW_STRESS"


def test_regime_call_skew_euphoria() -> None:
    snap = opt_engine.compute(_chain(otm_call_iv=0.56, otm_put_iv=0.50), now=_REF)  # skew +0.06
    assert snap.regime == "CALL_SKEW_EUPHORIA"


def test_regime_term_stress() -> None:
    snap = opt_engine.compute(_chain(atm_iv=0.55, long_atm_iv=0.50), now=_REF)  # slope −0.05
    assert snap.regime == "TERM_STRESS"


def test_regime_normal() -> None:
    snap = opt_engine.compute(_chain(atm_iv=0.50, long_atm_iv=0.50, realized=0.49), now=_REF)
    assert snap.regime == "NORMAL"


# ---------------- deribit adapter: parse, ağsız ----------------

def test_deribit_parses_instrument_and_iv(monkeypatch) -> None:
    def fake_json(url: str):
        return {
            "result": [
                {
                    "instrument_name": "BTC-27JUN25-60000-C",
                    "mark_iv": 55.0,
                    "open_interest": 1200.0,
                    "underlying_price": 60000.0,
                },
                {
                    "instrument_name": "BTC-27JUN25-54000-P",
                    "mark_iv": 62.0,
                    "open_interest": 900.0,
                    "underlying_price": 60000.0,
                },
            ]
        }

    monkeypatch.setattr(deribit, "_get_json", fake_json)
    chain = deribit.fetch("BTCUSD")
    assert chain is not None
    assert chain.underlying_price == 60000.0
    assert len(chain.quotes) == 2
    call = next(q for q in chain.quotes if q.option_type == "call")
    assert call.strike == 60000.0
    assert call.mark_iv == pytest.approx(0.55)  # yüzde puan → ondalık


def test_deribit_returns_none_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(deribit, "_get_json", lambda url: None)
    assert deribit.fetch("BTCUSD") is None


def test_deribit_unmapped_symbol_is_none() -> None:
    assert deribit.fetch("AAPL") is None


def test_deribit_skips_malformed_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        deribit,
        "_get_json",
        lambda url: {"result": [{"instrument_name": "garbage", "mark_iv": 50.0}]},
    )
    assert deribit.fetch("BTCUSD") is None  # parse edilemeyen → boş → None


# ---------------- orchestrator: crypto-only, DEGRADED, ağsız ----------------

def test_get_options_only_crypto_symbols() -> None:
    out = options_provider.get_options(["BTCUSD", "AAPL", "EURUSD"])
    assert set(out.keys()) <= options_provider.CRYPTO_SYMBOLS
    assert "AAPL" not in out


def test_fixture_mode_snapshot_is_unverified() -> None:
    # conftest TEST_USE_MOCK=true → fixture path; verified=False (karar dışı).
    out = options_provider.get_options(["BTCUSD"])
    snap = out["BTCUSD"]
    assert snap.status == "OK"
    assert snap.verified is False


def test_provider_failure_is_degraded_no_crash(monkeypatch) -> None:
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    monkeypatch.delenv("OPTIONS_USE_FIXTURE", raising=False)
    monkeypatch.setattr(deribit, "fetch", lambda s: None)
    options_provider.reset_provider_status()
    out = options_provider.get_options(["BTCUSD"])
    snap = out["BTCUSD"]
    assert snap.status == "DEGRADED"
    assert snap.verified is False
    assert snap.error
    status = options_provider.get_provider_status()
    assert status["options_deribit"]["status"] == "degraded"


def test_get_options_makes_no_network_call(monkeypatch) -> None:
    def _boom(*_a, **_k):  # pragma: no cover - çağrılmamalı
        raise AssertionError("options fixture modunda ağa çıkmamalı")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    out = options_provider.get_options(["BTCUSD"])
    assert out["BTCUSD"].symbol == "BTCUSD"


# ---------------- gate: yalnızca kısıtlayıcı ----------------

def _snap(
    *,
    regime: str = "NORMAL",
    verified: bool = True,
    status: str = "OK",
    atm_iv: float | None = 0.55,
    skew_25d: float | None = -0.05,
) -> OptionsSnapshot:
    return OptionsSnapshot(
        symbol="BTCUSD",
        regime=regime,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        verified=verified,
        atm_iv=atm_iv,
        skew_25d=skew_25d,
        is_proxy=True,
        source="test",
        evidence=["test"],
    )


def test_gate_none_when_no_data() -> None:
    assert options_risk.assess(None, "open_long").level == "NONE"


def test_gate_ignores_unverified_snapshot() -> None:
    v = options_risk.assess(_snap(regime="TERM_STRESS", verified=False), "open_long")
    assert v.level == "NONE"


def test_gate_ignores_degraded_snapshot() -> None:
    v = options_risk.assess(_snap(regime="TERM_STRESS", status="DEGRADED"), "open_long")
    assert v.level == "NONE"


def test_gate_put_skew_long_is_caution() -> None:
    v = options_risk.assess(_snap(regime="PUT_SKEW_STRESS"), "open_long")
    assert v.level == "CAUTION"
    assert v.size_factor == 0.5
    # short/contrarian → yalnızca bağlam (WATCH, size değişmez).
    short = options_risk.assess(_snap(regime="PUT_SKEW_STRESS"), "open_short")
    assert short.level == "WATCH"
    assert short.size_factor == 1.0


def test_gate_call_skew_euphoria_long_chase_is_caution() -> None:
    v = options_risk.assess(_snap(regime="CALL_SKEW_EUPHORIA"), "open_long")
    assert v.level == "CAUTION"
    assert v.size_factor == 0.5


def test_gate_term_stress_blocks_position_increase() -> None:
    v = options_risk.assess(_snap(regime="TERM_STRESS"), "open_long")
    assert v.level == "NO_POSITION_INCREASE"
    assert v.block is True
    assert v.size_factor == 0.0


def test_gate_rich_vol_is_caution() -> None:
    v = options_risk.assess(_snap(regime="RICH_VOL"), "open_long")
    assert v.level == "CAUTION"
    assert v.size_factor == 0.5


def test_gate_cheap_vol_is_context_only_no_boost() -> None:
    v = options_risk.assess(_snap(regime="CHEAP_VOL"), "open_long")
    assert v.level == "WATCH"
    assert v.size_factor == 1.0  # asla boost


def test_gate_normal_is_none() -> None:
    assert options_risk.assess(_snap(regime="NORMAL"), "open_long").level == "NONE"


def test_gate_never_boosts_size() -> None:
    for regime in ("NORMAL", "RICH_VOL", "CHEAP_VOL", "PUT_SKEW_STRESS", "CALL_SKEW_EUPHORIA", "TERM_STRESS"):
        for action in ("open_long", "open_short"):
            v = options_risk.assess(_snap(regime=regime), action)
            assert v.size_factor <= 1.0


# ---------------- gate: timeframe ağırlığı ----------------

def test_timeframe_weight_context_profile() -> None:
    # options 4h/1d/1w bağlamı: 1d/1w tam, 15m düşük.
    assert options_risk.timeframe_weight("1d") == 1.0
    assert options_risk.timeframe_weight("1w") == 1.0
    assert options_risk.timeframe_weight("15m") == 0.25


def test_apply_timeframe_full_weight_keeps_block() -> None:
    term = options_risk.assess(_snap(regime="TERM_STRESS"), "open_long")
    kept = options_risk.apply_timeframe(term, options_risk.timeframe_weight("1d"))
    assert kept.block is True
    assert kept.level == "NO_POSITION_INCREASE"


def test_apply_timeframe_softens_block_on_low_weight() -> None:
    term = options_risk.assess(_snap(regime="TERM_STRESS"), "open_long")
    softened = options_risk.apply_timeframe(term, options_risk.timeframe_weight("15m"))
    assert softened.block is False
    assert softened.level == "CAUTION"
    assert softened.size_factor <= 1.0


# ---------------- decide_matrix entegrasyonu (uçtan uca) ----------------

def _risk_in(dqs: float = 90.0) -> RiskInput:
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


def _force_bullish(snap, symbol: str = "BTCUSD") -> None:
    for tf in ("15m", "1h", "4h", "1d", "1w"):
        snap.technicals_by_tf[symbol][tf] = TechnicalSnapshot(
            symbol=symbol, timeframe=tf, rsi=85.0, macd=2.0, atr=1.0,
            ema_stack="bullish", score=95.0, status="OK",
        )
    snap.technicals[symbol] = snap.technicals_by_tf[symbol]["1d"]


def test_matrix_term_stress_blocks_open_cell(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.options["BTCUSD"] = _snap(regime="TERM_STRESS", verified=True)
    regime, risk, decisions = decide_matrix(
        ["BTCUSD"], snap, _risk_in(), timeframes=["1d"]
    )
    d = decisions[0]
    assert d.action == "hold"
    assert any(b.startswith("options_risk:") for b in d.blocked_by)
    assert d.options_report.get("regime") == "TERM_STRESS"

    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"], timeframes=["1d"])
    assert any(s["symbol"] == "BTCUSD" for s in view["options"])
    assert any(
        b.startswith("options_risk:") for c in view["cells"] for b in c["blocked_by"]
    )


def test_matrix_cheap_vol_is_context_only_keeps_open(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    base = build_snapshot(["BTCUSD"])
    _force_bullish(base)
    base.options.clear()
    _r, _k, baseline = decide_matrix(["BTCUSD"], base, _risk_in(), timeframes=["1d"])

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.options["BTCUSD"] = _snap(regime="CHEAP_VOL", verified=True)
    _r, _k, dec = decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["1d"])

    assert baseline[0].action == "open_long"
    assert dec[0].action == "open_long"  # açılış korunur
    # CHEAP_VOL yalnızca bağlam (WATCH) → size ARTMAZ, azalmaz da.
    assert dec[0].size_multiplier <= baseline[0].size_multiplier


def test_matrix_unverified_options_does_not_block(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.options["BTCUSD"] = _snap(regime="TERM_STRESS", verified=False)
    _regime, _risk, decisions = decide_matrix(
        ["BTCUSD"], snap, _risk_in(), timeframes=["1d"]
    )
    assert decisions[0].action == "open_long"
    assert not any(
        b.startswith("options_risk:") for d in decisions for b in d.blocked_by
    )


def test_matrix_dqs_blocked_takes_precedence_no_options_bypass(paper_env) -> None:
    # DQS düşük → risk gate hücreyi kıstırır; options bunu bypass/override edemez.
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.options["BTCUSD"] = _snap(regime="CHEAP_VOL", verified=True)  # "boost" denemesi
    _regime, _risk, decisions = decide_matrix(
        ["BTCUSD"], snap, _risk_in(dqs=10.0), timeframes=["1d"]
    )
    d = decisions[0]
    assert d.action in ("hold", "blocked")  # düşük DQS → açılış yok
    assert d.actionable is False
    # Kıstıran kapı risk_gate (options değil) — options hard gate'i bypass etmez.
    assert any(b.startswith("risk_gate:") for b in d.blocked_by)
    assert not any(b.startswith("options_risk:") for b in d.blocked_by)
