"""v2.7 D2 — Crypto Derivatives Intelligence testleri.

Hepsi offline (live network yok). Doğrulanan invariant'lar:

- Ham funding/OI parse (Binance adapter, monkeypatch ile ağsız).
- Sağlayıcı başarısız → DEGRADED snapshot (mock yok, crash yok).
- Squeeze proxy / funding bias deterministik; squeeze GERÇEK liq değil (is_proxy).
- Gate yalnızca KISITLAYICI: HIGH squeeze → NO_POSITION_INCREASE (block);
  ELEVATED → CAUTION ×0.5; funding chase (aynı yön) → CAUTION; contrarian → NONE.
- Gate ASLA size artırmaz (size_factor ≤ 1.0).
- Timeframe ağırlığı: 1w → etki yok; düşük ağırlık (1d) block'u CAUTION'a yumuşatır.
- Yalnızca kripto sembolleri işlenir.
- Doğrulanmamış (fixture) snapshot karar zincirine GİRMEZ; yalnızca bağlam.
- decide_matrix entegrasyonu: verified HIGH squeeze → hücre blocked_by ile durur.
"""
from __future__ import annotations

import importlib
import urllib.request

import pytest

from packages.data.providers import derivatives as deriv_provider
from packages.data.providers.derivatives import binance, fixtures
from packages.data.providers.derivatives import engine as deriv_engine
from packages.data.types import DerivativesSnapshot, TechnicalSnapshot
from packages.risk import derivatives_risk
from packages.risk.engine import RiskInput

# ---------------- engine: parse + squeeze proxy ----------------

def _input(**kw) -> deriv_engine.DerivInput:
    base = dict(
        symbol="BTCUSD",
        funding_rate=0.0002,
        open_interest_usd=9_000_000_000.0,
        oi_change_pct=0.01,
        price_momentum_pct=0.0,
        volatility_pct=0.01,
        source="test",
        verified=True,
    )
    base.update(kw)
    return deriv_engine.DerivInput(**base)


def test_compute_ok_with_funding_and_oi() -> None:
    snap = deriv_engine.compute(_input())
    assert snap.status == "OK"
    assert snap.is_proxy is True  # squeeze her zaman proxy (gerçek liq değil)
    assert 0.0 <= snap.squeeze_proxy <= 100.0
    assert snap.funding_annualized is not None
    assert snap.evidence


def test_compute_missing_essential_is_degraded() -> None:
    # funding YA DA open_interest yoksa → DEGRADED (karar dışı), crash yok.
    no_funding = deriv_engine.compute(_input(funding_rate=None))
    assert no_funding.status == "DEGRADED"
    assert no_funding.error
    no_oi = deriv_engine.compute(_input(open_interest_usd=None))
    assert no_oi.status == "DEGRADED"


def test_funding_bias_thresholds() -> None:
    assert deriv_engine.compute(_input(funding_rate=0.0006)).funding_bias == "crowded_long"
    assert deriv_engine.compute(_input(funding_rate=-0.0006)).funding_bias == "crowded_short"
    assert deriv_engine.compute(_input(funding_rate=0.0001)).funding_bias == "neutral"


def test_high_squeeze_when_all_components_extreme() -> None:
    # Aşırı funding + OI artışı + crowd'a karşı momentum + yüksek vol → HIGH.
    snap = deriv_engine.compute(
        _input(
            funding_rate=0.0012,          # crowded_long, extreme
            oi_change_pct=0.08,           # OI surge
            price_momentum_pct=-0.05,     # long crowd + düşüş = adverse
            volatility_pct=0.06,
        )
    )
    assert snap.squeeze_level == "HIGH"
    assert snap.squeeze_proxy >= 75.0


def test_low_squeeze_when_calm() -> None:
    snap = deriv_engine.compute(
        _input(funding_rate=0.0001, oi_change_pct=0.0, price_momentum_pct=0.0, volatility_pct=0.0)
    )
    assert snap.squeeze_level == "NONE"


def test_compute_is_deterministic() -> None:
    inp = _input(funding_rate=0.0008, oi_change_pct=0.04)
    assert deriv_engine.compute(inp).squeeze_proxy == deriv_engine.compute(inp).squeeze_proxy


# ---------------- binance adapter: parse, ağsız ----------------

def test_binance_parses_funding_and_oi(monkeypatch) -> None:
    def fake_json(url: str):
        if "premiumIndex" in url:
            return {"lastFundingRate": "0.00045"}
        if "openInterestHist" in url:
            return [
                {"sumOpenInterestValue": "9000000000"},
                {"sumOpenInterestValue": "9180000000"},
            ]
        return None

    monkeypatch.setattr(binance, "_get_json", fake_json)
    raw = binance.fetch("BTCUSD")
    assert raw is not None
    assert abs(raw.funding_rate - 0.00045) < 1e-9
    assert raw.open_interest_usd == 9_180_000_000.0
    assert raw.oi_change_pct is not None and raw.oi_change_pct > 0


def test_binance_returns_none_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(binance, "_get_json", lambda url: None)
    assert binance.fetch("BTCUSD") is None


def test_binance_unmapped_symbol_is_none() -> None:
    assert binance.fetch("AAPL") is None


def test_fixtures_are_offline_and_supported() -> None:
    assert fixtures.fetch("BTCUSD") is not None
    assert fixtures.fetch("AAPL") is None


# ---------------- orchestrator: crypto-only, DEGRADED, ağsız ----------------

def test_get_derivatives_only_crypto_symbols() -> None:
    out = deriv_provider.get_derivatives(["BTCUSD", "AAPL", "EURUSD"])
    assert set(out.keys()) <= deriv_provider.CRYPTO_SYMBOLS
    assert "AAPL" not in out


def test_fixture_mode_snapshot_is_unverified() -> None:
    # conftest TEST_USE_MOCK=true → fixture path; verified=False (karar dışı).
    out = deriv_provider.get_derivatives(["BTCUSD"])
    snap = out["BTCUSD"]
    assert snap.status == "OK"
    assert snap.verified is False  # fixture asla karar zincirine girmez


def test_provider_failure_is_degraded_no_crash(monkeypatch) -> None:
    # Live path (fixture kapalı) + provider None → DEGRADED, mock yok.
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    monkeypatch.delenv("DERIVATIVES_USE_FIXTURE", raising=False)
    monkeypatch.setattr(binance, "fetch", lambda s: None)
    deriv_provider.reset_provider_status()
    out = deriv_provider.get_derivatives(["BTCUSD"])
    snap = out["BTCUSD"]
    assert snap.status == "DEGRADED"
    assert snap.verified is False
    assert snap.error
    status = deriv_provider.get_provider_status()
    assert status["derivatives_binance"]["status"] == "degraded"


def test_get_derivatives_makes_no_network_call(monkeypatch) -> None:
    def _boom(*_a, **_k):  # pragma: no cover - çağrılmamalı
        raise AssertionError("derivatives fixture modunda ağa çıkmamalı")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    out = deriv_provider.get_derivatives(["BTCUSD"])  # fixture mode
    assert out["BTCUSD"].symbol == "BTCUSD"


# ---------------- gate: yalnızca kısıtlayıcı ----------------

def _snap(
    *,
    squeeze_level: str = "NONE",
    funding_bias: str = "neutral",
    funding_rate: float | None = 0.0001,
    verified: bool = True,
    status: str = "OK",
    proxy: float = 10.0,
) -> DerivativesSnapshot:
    return DerivativesSnapshot(
        symbol="BTCUSD",
        funding_rate=funding_rate,
        open_interest_usd=9_000_000_000.0,
        squeeze_proxy=proxy,
        squeeze_level=squeeze_level,  # type: ignore[arg-type]
        funding_bias=funding_bias,    # type: ignore[arg-type]
        is_proxy=True,
        status=status,                # type: ignore[arg-type]
        source="test",
        verified=verified,
        evidence=["test"],
    )


def test_gate_none_when_no_data() -> None:
    assert derivatives_risk.assess(None, "open_long").level == "NONE"


def test_gate_ignores_unverified_snapshot() -> None:
    v = derivatives_risk.assess(_snap(squeeze_level="HIGH", verified=False), "open_long")
    assert v.level == "NONE"  # fixture/test verisi karar zincirine girmez


def test_gate_ignores_degraded_snapshot() -> None:
    v = derivatives_risk.assess(_snap(squeeze_level="HIGH", status="DEGRADED"), "open_long")
    assert v.level == "NONE"


def test_gate_high_squeeze_blocks_position_increase() -> None:
    v = derivatives_risk.assess(_snap(squeeze_level="HIGH", proxy=80.0), "open_long")
    assert v.level == "NO_POSITION_INCREASE"
    assert v.block is True
    assert v.size_factor == 0.0


def test_gate_elevated_squeeze_is_caution_half_size() -> None:
    v = derivatives_risk.assess(_snap(squeeze_level="ELEVATED", proxy=60.0), "open_long")
    assert v.level == "CAUTION"
    assert v.block is False
    assert v.size_factor == 0.5


def test_gate_funding_chase_same_direction_is_caution() -> None:
    long_chase = derivatives_risk.assess(
        _snap(funding_bias="crowded_long", funding_rate=0.0008), "open_long"
    )
    assert long_chase.level == "CAUTION"
    short_chase = derivatives_risk.assess(
        _snap(funding_bias="crowded_short", funding_rate=-0.0008), "open_short"
    )
    assert short_chase.level == "CAUTION"


def test_gate_contrarian_is_context_only_no_boost() -> None:
    # crowded_short + open_long (contrarian) → NONE; asla boost yok.
    v = derivatives_risk.assess(_snap(funding_bias="crowded_short"), "open_long")
    assert v.level == "NONE"
    assert v.size_factor == 1.0


def test_gate_never_boosts_size() -> None:
    for level in ("NONE", "LOW", "ELEVATED", "HIGH"):
        v = derivatives_risk.assess(_snap(squeeze_level=level, proxy=50.0), "open_long")
        assert v.size_factor <= 1.0


# ---------------- gate: timeframe ağırlığı ----------------

def test_timeframe_weight_weekly_is_zero() -> None:
    assert derivatives_risk.timeframe_weight("1w") == 0.0
    assert derivatives_risk.timeframe_weight("1h") == 1.0


def test_apply_timeframe_softens_block_on_low_weight() -> None:
    high = derivatives_risk.assess(_snap(squeeze_level="HIGH", proxy=80.0), "open_long")
    # 1d ağırlığı (0.5) < block eşiği (0.75) → block CAUTION'a yumuşar.
    softened = derivatives_risk.apply_timeframe(high, derivatives_risk.timeframe_weight("1d"))
    assert softened.block is False
    assert softened.level == "CAUTION"
    assert softened.size_factor <= 1.0


def test_apply_timeframe_full_weight_keeps_block() -> None:
    high = derivatives_risk.assess(_snap(squeeze_level="HIGH", proxy=80.0), "open_long")
    kept = derivatives_risk.apply_timeframe(high, 1.0)
    assert kept.block is True
    assert kept.level == "NO_POSITION_INCREASE"


def test_apply_timeframe_zero_weight_disables_effect() -> None:
    high = derivatives_risk.assess(_snap(squeeze_level="HIGH", proxy=80.0), "open_long")
    off = derivatives_risk.apply_timeframe(high, 0.0)
    assert off.level == "NONE"
    assert off.block is False


# ---------------- decide_matrix entegrasyonu (uçtan uca) ----------------
#
# Türev gate yalnızca GERÇEK bir açılış adayına (open_long/open_short) etki eder
# (hold'da pozisyon yok → etki yok). Bu yüzden teknikleri güçlü bullish'e
# sabitleyip (consensus → open_long) gate'in açılışı kıstığını doğruluyoruz.


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
    """Tüm TF tekniklerini güçlü bullish yap → consensus open_long üretir."""
    for tf in ("15m", "1h", "4h", "1d", "1w"):
        snap.technicals_by_tf[symbol][tf] = TechnicalSnapshot(
            symbol=symbol, timeframe=tf, rsi=85.0, macd=2.0, atr=1.0,
            ema_stack="bullish", score=95.0, status="OK",
        )
    snap.technicals[symbol] = snap.technicals_by_tf[symbol]["1d"]


def test_matrix_high_squeeze_blocks_open_cell(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    # Verified HIGH squeeze enjekte et (fixture'ın verified=False'unu ezer).
    snap.derivatives["BTCUSD"] = _snap(squeeze_level="HIGH", proxy=82.0, verified=True)
    regime, risk, decisions = decide_matrix(
        ["BTCUSD"], snap, _risk_in(), timeframes=["1h"]
    )
    d = decisions[0]
    assert d.action == "hold"  # NO_POSITION_INCREASE → açılış durdu
    assert any(b.startswith("derivatives_risk:") for b in d.blocked_by)
    assert d.derivatives_report.get("squeeze_level") == "HIGH"

    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"], timeframes=["1h"])
    assert any(s["symbol"] == "BTCUSD" for s in view["derivatives"])
    assert any(
        b.startswith("derivatives_risk:") for c in view["cells"] for b in c["blocked_by"]
    )


def test_matrix_caution_reduces_size_but_keeps_open(paper_env) -> None:
    # ELEVATED squeeze (CAUTION ×0.5) → açılış kalır ama size küçülür (asla artmaz).
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    base_snap = build_snapshot(["BTCUSD"])
    _force_bullish(base_snap)
    base_snap.derivatives.clear()  # türev etkisi yok → baseline size
    _r, _k, base = decide_matrix(["BTCUSD"], base_snap, _risk_in(), timeframes=["1h"])

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.derivatives["BTCUSD"] = _snap(squeeze_level="ELEVATED", proxy=60.0, verified=True)
    _r, _k, dec = decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["1h"])

    assert base[0].action == "open_long"
    assert dec[0].action == "open_long"  # açılış korunur
    assert dec[0].derivatives_report.get("level") == "CAUTION"
    assert dec[0].size_multiplier < base[0].size_multiplier  # küçüldü, artmadı


def test_matrix_unverified_derivatives_does_not_block_open(paper_env) -> None:
    # Fixture/test verisi (verified=False) açılışı bloklayamaz; yalnızca bağlam.
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.derivatives["BTCUSD"] = _snap(squeeze_level="HIGH", proxy=82.0, verified=False)
    regime, risk, decisions = decide_matrix(
        ["BTCUSD"], snap, _risk_in(), timeframes=["1h"]
    )
    assert decisions[0].action == "open_long"  # unverified → bloklamadı
    assert not any(
        b.startswith("derivatives_risk:") for d in decisions for b in d.blocked_by
    )
    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"], timeframes=["1h"])
    # status=OK → banner'da bağlam olarak görünür ama verified=False damgalı.
    btc = next(s for s in view["derivatives"] if s["symbol"] == "BTCUSD")
    assert btc["verified"] is False
