"""v2.7 D5 — Catalyst half-life intelligence testleri.

Hepsi offline (live network YOK). Doğrulanan invariant'lar:

- Başlık → deterministik event_type (kural tabanlı, LLM yok).
- Ateşkes → Brent/Gold/BTC etkilenen + kısa yarı-ömür; CPI → whipsaw/CAUTION.
- Rumor → verified=False + CONTEXT_ONLY (trade'e dönüşmez).
- Gate yalnızca KISITLAYICI: CAUTION → ×0.5; NO_POSITION_INCREASE → block;
  ASLA size artırmaz (size_factor ≤ 1.0). Yön bağımsız.
- Yarı-ömrü dolmuş / verified=False / sembol-TF dışı impact karar zincirine girmez.
- decide_matrix: verified yüksek-etki → hücre WATCH/CAUTION/block; DQS BLOCKED /
  KILL_SWITCH her zaman finaldir (catalyst bypass etmez).
"""
from __future__ import annotations

import importlib
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers.news import catalyst as cat
from packages.data.types import CatalystImpact, NewsHeadline, TechnicalSnapshot
from packages.risk import catalyst_risk
from packages.risk.engine import RiskInput

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _h(
    title: str,
    *,
    sentiment: str = "neutral",
    verified: bool = True,
    region: str | None = None,
    age_min: float = 1.0,
    source: str = "Reuters",
) -> NewsHeadline:
    return NewsHeadline(
        id="hid_" + str(abs(hash(title)) % 10_000),
        source=source,
        region=region,
        ts=_NOW - timedelta(minutes=age_min),
        title=title,
        sentiment=sentiment,  # type: ignore[arg-type]
        verified=verified,
        freshness="FRESH",
    )


# ---------------- classification ----------------

def test_classify_event_types() -> None:
    assert cat.classify_event_type("Israel and Hamas agree ceasefire deal") == (
        "geopolitical_deescalation"
    )
    assert cat.classify_event_type("Iran launches missile strike on base") == (
        "geopolitical_escalation"
    )
    assert cat.classify_event_type("US CPI rises more than expected") == "inflation_data"
    assert cat.classify_event_type("US nonfarm payrolls smash forecasts") == "jobs_data"
    assert cat.classify_event_type("FOMC holds rates, Powell signals patience") == (
        "central_bank"
    )
    assert cat.classify_event_type("OPEC+ announces surprise production cut") == "oil_supply"
    assert cat.classify_event_type("EIA crude inventory draws sharply") == "oil_inventory"
    assert cat.classify_event_type("Bitcoin spot ETF flows turn positive") == "crypto_etf_flow"
    assert cat.classify_event_type("BTC funding rate spikes, liquidation cascade") == (
        "funding_oi_squeeze"
    )
    assert cat.classify_event_type("Major exchange halts withdrawals after hack") == (
        "exchange_outage"
    )
    assert cat.classify_event_type("Random lifestyle update about nothing") == "unknown"


def test_rumor_detection_overrides_event_type() -> None:
    h = _h("Sources say Fed may cut rates next week (unconfirmed)")
    imp = cat.build_impact(h, now=_NOW)
    assert imp.event_type == "rumor_unverified"
    assert imp.verified is False          # söylenti trade'e dönüşmez
    assert imp.actionability == "CONTEXT_ONLY"


# ---------------- ceasefire (de-escalation) ----------------

def test_ceasefire_affected_assets_and_short_half_life() -> None:
    h = _h("Israel and Iran agree ceasefire, oil risk premium unwinds",
           sentiment="bullish", region="Middle East")
    imp = cat.build_impact(h, now=_NOW)
    assert imp.event_type == "geopolitical_deescalation"
    # Brent + Gold + BTC etkilenen (risk-premium unwind / hedge unwind / risk-on).
    for sym in ("BRENT", "XAUUSD", "BTCUSD"):
        assert sym in imp.affected_assets
    # Kısa yarı-ömür + valid_until ileri tarih.
    assert imp.expected_half_life_minutes <= 120
    assert imp.valid_until is not None and imp.valid_until > h.ts
    # 15m/1h/4h whipsaw penceresi.
    assert "15m" in imp.affected_timeframes and "1h" in imp.affected_timeframes


# ---------------- CPI (inflation) whipsaw ----------------

def test_cpi_is_caution_whipsaw() -> None:
    imp = cat.build_impact(_h("US CPI inflation comes in line", sentiment="neutral"), now=_NOW)
    assert imp.event_type == "inflation_data"
    assert imp.actionability in ("CAUTION", "NO_POSITION_INCREASE")
    assert "15m" in imp.affected_timeframes  # ilk reaksiyon whipsaw
    assert imp.verified is True


def test_high_surprise_escalates_actionability() -> None:
    hot = cat.build_impact(
        _h("US CPI surges, hotter-than-expected shock", sentiment="bearish"), now=_NOW
    )
    assert abs(hot.surprise_level) >= 0.7
    assert hot.actionability == "NO_POSITION_INCREASE"  # CAUTION → yükseldi


# ---------------- build_impacts (pure, no network) ----------------

def test_build_impacts_no_network(monkeypatch) -> None:
    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("catalyst engine ağ çağrısı yapmamalı")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    headlines = [
        _h("US CPI rises sharply", sentiment="bearish"),
        _h("Israel ceasefire holds", sentiment="bullish"),
        _h("Sources say merger rumored", sentiment="neutral"),
    ]
    impacts = cat.build_impacts(headlines, now=_NOW)
    assert impacts  # üretildi
    # En kısıtlayıcı önce sıralanır.
    assert impacts[0].actionability != "CONTEXT_ONLY"
    # Rumor verified=False kaldı.
    assert any(i.event_type == "rumor_unverified" and not i.verified for i in impacts)


def test_unverified_headline_yields_context_only() -> None:
    imp = cat.build_impact(_h("US CPI rises", verified=False), now=_NOW)
    assert imp.verified is False
    assert imp.actionability == "CONTEXT_ONLY"


# ---------------- gate: yalnızca kısıtlayıcı ----------------

def _impact(
    *,
    action: str = "CAUTION",
    assets: list[str] | None = None,
    tfs: list[str] | None = None,
    verified: bool = True,
    valid_min_ahead: float = 60.0,
    event_type: str = "inflation_data",
) -> CatalystImpact:
    return CatalystImpact(
        catalyst_id="cat::x",
        headline_id="x",
        event_type=event_type,  # type: ignore[arg-type]
        affected_assets=assets or ["BTCUSD"],
        affected_timeframes=tfs or ["1h"],  # type: ignore[arg-type]
        expected_half_life_minutes=90,
        valid_until=_NOW + timedelta(minutes=valid_min_ahead),
        actionability=action,  # type: ignore[arg-type]
        verified=verified,
        ts=_NOW,
    )


def test_gate_none_when_empty() -> None:
    assert catalyst_risk.assess(None, "BTCUSD", "1h", now=_NOW).level == "NONE"
    assert catalyst_risk.assess([], "BTCUSD", "1h", now=_NOW).level == "NONE"


def test_gate_ignores_unverified() -> None:
    v = catalyst_risk.assess([_impact(action="NO_POSITION_INCREASE", verified=False)],
                             "BTCUSD", "1h", now=_NOW)
    assert v.level == "NONE"  # rumor/fixture karar zincirine girmez


def test_gate_ignores_expired_half_life() -> None:
    v = catalyst_risk.assess([_impact(action="NO_POSITION_INCREASE", valid_min_ahead=-10)],
                             "BTCUSD", "1h", now=_NOW)
    assert v.level == "NONE"  # yarı-ömür doldu → yalnızca bağlam


def test_gate_ignores_other_symbol_or_tf() -> None:
    imp = _impact(action="CAUTION", assets=["ETHUSD"], tfs=["1h"])
    assert catalyst_risk.assess([imp], "BTCUSD", "1h", now=_NOW).level == "NONE"
    imp2 = _impact(action="CAUTION", assets=["BTCUSD"], tfs=["4h"])
    assert catalyst_risk.assess([imp2], "BTCUSD", "1h", now=_NOW).level == "NONE"


def test_gate_caution_half_size() -> None:
    v = catalyst_risk.assess([_impact(action="CAUTION")], "BTCUSD", "1h", now=_NOW)
    assert v.level == "CAUTION"
    assert v.size_factor == 0.5
    assert v.block is False


def test_gate_block_stops_open() -> None:
    v = catalyst_risk.assess([_impact(action="NO_POSITION_INCREASE")], "BTCUSD", "1h", now=_NOW)
    assert v.level == "NO_POSITION_INCREASE"
    assert v.block is True
    assert v.size_factor == 0.0


def test_gate_context_only_has_no_effect() -> None:
    v = catalyst_risk.assess([_impact(action="CONTEXT_ONLY")], "BTCUSD", "1h", now=_NOW)
    assert v.level == "NONE"


def test_gate_never_boosts() -> None:
    for action in ("CONTEXT_ONLY", "WATCH", "CAUTION", "NO_POSITION_INCREASE"):
        v = catalyst_risk.assess([_impact(action=action)], "BTCUSD", "1h", now=_NOW)
        assert v.size_factor <= 1.0


def test_gate_most_restrictive_wins() -> None:
    impacts = [_impact(action="WATCH"), _impact(action="NO_POSITION_INCREASE")]
    v = catalyst_risk.assess(impacts, "BTCUSD", "1h", now=_NOW)
    assert v.level == "NO_POSITION_INCREASE"


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


def _live_impact(action: str) -> CatalystImpact:
    # valid_until uzak gelecekte → her zaman aktif (test determinizmi).
    return CatalystImpact(
        catalyst_id="cat::live",
        headline_id="live",
        event_type="inflation_data",
        affected_assets=["BTCUSD"],
        affected_timeframes=["1h"],
        expected_half_life_minutes=90,
        valid_until=datetime.now(UTC) + timedelta(hours=12),
        actionability=action,  # type: ignore[arg-type]
        verified=True,
        ts=datetime.now(UTC),
    )


def test_matrix_caution_catalyst_reduces_size(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    base = build_snapshot(["BTCUSD"])
    _force_bullish(base)
    base.catalyst_impacts = []
    _r, _k, base_dec = decide_matrix(["BTCUSD"], base, _risk_in(), timeframes=["1h"])

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.catalyst_impacts = [_live_impact("CAUTION")]
    _r, _k, dec = decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["1h"])

    assert base_dec[0].action == "open_long"
    assert dec[0].action == "open_long"  # açılış korunur (WATCH/CAUTION)
    assert dec[0].catalyst_report.get("level") == "CAUTION"
    assert dec[0].size_multiplier < base_dec[0].size_multiplier


def test_matrix_block_catalyst_stops_open(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.catalyst_impacts = [_live_impact("NO_POSITION_INCREASE")]
    regime, risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["1h"])
    d = decisions[0]
    assert d.action == "hold"
    assert any(b.startswith("catalyst_risk:") for b in d.blocked_by)

    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"], timeframes=["1h"])
    assert any(c["event_type"] == "inflation_data" for c in view["catalysts"])
    assert any(
        b.startswith("catalyst_risk:") for c in view["cells"] for b in c["blocked_by"]
    )


def test_matrix_rumor_does_not_block(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    # verified=False (rumor) → karar zincirine girmez.
    rumor = _live_impact("NO_POSITION_INCREASE")
    rumor.verified = False
    rumor.event_type = "rumor_unverified"
    rumor.actionability = "CONTEXT_ONLY"
    snap.catalyst_impacts = [rumor]
    _r, _k, decisions = decide_matrix(["BTCUSD"], snap, _risk_in(), timeframes=["1h"])
    assert decisions[0].action == "open_long"
    assert not any(
        b.startswith("catalyst_risk:") for d in decisions for b in d.blocked_by
    )


def test_matrix_dqs_blocked_overrides_catalyst(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix, matrix_view

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.catalyst_impacts = [_live_impact("NO_POSITION_INCREASE")]
    regime, risk, decisions = decide_matrix(
        ["BTCUSD"], snap, _risk_in(dqs=40.0), timeframes=["1h"]
    )
    view = matrix_view(regime, risk, decisions, snap, ["BTCUSD"], timeframes=["1h"])
    assert view["suspended"] is True
    assert decisions[0].action != "open_long"
    # DQS BLOCKED hard gate önce döner → blocked_by risk_gate (catalyst değil).
    assert any(b.startswith("risk_gate:") for b in decisions[0].blocked_by)


def test_matrix_kill_switch_overrides_catalyst(paper_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_matrix

    snap = build_snapshot(["BTCUSD"])
    _force_bullish(snap)
    snap.catalyst_impacts = [_live_impact("CAUTION")]
    _r, risk, decisions = decide_matrix(
        ["BTCUSD"], snap, _risk_in(daily_pnl=-9000.0), timeframes=["1h"]
    )
    assert risk.action == "KILL_SWITCH"
    assert decisions[0].action == "blocked"
