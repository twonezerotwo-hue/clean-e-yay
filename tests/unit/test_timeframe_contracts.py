"""T0 — Timeframe contract seeding testleri.

- Legacy Position/Trade kayıtları (timeframe alanı olmadan) default "1d"
  ile yüklenir — kırılma yok.
- TechnicalSnapshot 15m ve 1w kabul eder; provider passthrough yapar.
- Fingerprint v2 timeframe segmenti taşır; legacy formatla çakışmaz;
  MIN_TRADES altında NEUTRAL fallback korunur.
- thresholds timeframe_risk politikası: 1w doğrudan paper execution yok;
  multiplier'lar asla 1.0'ı aşmaz (sadece risk azaltıcı).
- Runtime davranış değişmedi: technicals_by_tf None, TradeDecision
  timeframe default "1d".
"""
from __future__ import annotations

import dataclasses
import importlib

import pytest


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


# ---------------- legacy compatibility ----------------

def test_legacy_position_and_trade_load_default_1d(fresh_env) -> None:
    ps = fresh_env
    legacy_pos = {
        "id": "p1", "symbol": "BTCUSD", "side": "long",
        "entry_price": 100.0, "current_price": 101.0, "size_usd": 1000.0,
        "sl": 96.0, "tp": 108.0, "opened_at": "2026-06-01T00:00:00+00:00",
    }
    legacy_trade = {
        "id": "t1", "symbol": "BTCUSD", "side": "long",
        "entry_price": 100.0, "exit_price": 102.0, "pnl_usd": 20.0,
        "opened_at": "2026-06-01T00:00:00+00:00",
        "closed_at": "2026-06-01T01:00:00+00:00",
        "close_reason": "TP_HIT",
    }
    state = ps.PaperState.from_dict(
        {
            "equity_usd": 100000, "peak_equity_usd": 100000,
            "open_positions": [legacy_pos], "recent_trades": [legacy_trade],
        }
    )
    assert state.open_positions[0].timeframe == "1d"
    assert state.recent_trades[0].timeframe == "1d"
    # Round-trip: to_dict artık timeframe içerir, tekrar yüklenebilir
    state2 = ps.PaperState.from_dict(state.to_dict())
    assert state2.open_positions[0].timeframe == "1d"


# ---------------- TechnicalSnapshot + provider ----------------

def test_technical_snapshot_accepts_15m_and_1w() -> None:
    from packages.data.types import TIMEFRAMES, TechnicalSnapshot
    assert TIMEFRAMES == ("15m", "1h", "4h", "1d", "1w")
    for tf in ("15m", "1w"):
        snap = TechnicalSnapshot(symbol="BTCUSD", timeframe=tf)
        assert snap.timeframe == tf
    assert TechnicalSnapshot(symbol="BTCUSD").timeframe == "1d"


def test_technical_provider_passthrough_all_timeframes() -> None:
    from packages.data.providers import technical
    for tf in ("15m", "1h", "4h", "1d", "1w"):
        assert technical.get_snapshot("BTCUSD", tf).timeframe == tf
    # Bilinmeyen → "1d" (güvenli fallback)
    assert technical.get_snapshot("BTCUSD", "3m").timeframe == "1d"


def test_market_snapshot_technicals_by_tf_filled() -> None:
    # T0'da None idi; T1 ile gerçek (test modunda fixture) OHLCV'den dolar.
    from packages.data.ingestion.pipeline import build_snapshot
    snap = build_snapshot(["BTCUSD"])
    assert snap.technicals_by_tf is not None
    assert set(snap.technicals_by_tf["BTCUSD"].keys()) == {"15m", "1h", "4h", "1d", "1w"}
    assert snap.technicals["BTCUSD"].timeframe == "1d"  # legacy alan değişmedi


# ---------------- fingerprint v2 ----------------

def test_fingerprint_v2_includes_timeframe() -> None:
    from packages.learning import fingerprint as fpm
    fp = fpm.make(
        symbol="BTCUSD", regime="NEUTRAL", direction="bullish",
        score=72.0, confluence=True, dominant_module="touche",
    )
    parts = fp.split("|")
    assert parts[0] == "BTCUSD"
    assert parts[1] == "v2"
    assert parts[2] == "1d"  # default
    assert fpm.is_v2(fp)

    fp15 = fpm.make(
        symbol="BTCUSD", regime="NEUTRAL", direction="bullish",
        score=72.0, confluence=True, dominant_module="touche",
        timeframe="15m",
    )
    assert fp15.split("|")[2] == "15m"
    assert fp15 != fp


def test_legacy_fingerprint_does_not_collide_with_v2(fresh_env) -> None:
    from packages.learning import fingerprint as fpm
    from packages.learning import mistake_memory as mm

    legacy = "BTCUSD|NEUTRAL|bullish|S65|C|touche"  # eski format
    v2 = fpm.make(
        symbol="BTCUSD", regime="NEUTRAL", direction="bullish",
        score=72.0, confluence=True, dominant_module="touche",
    )
    assert legacy != v2
    assert not fpm.is_v2(legacy)

    # Legacy kayıtlar v2 lookup'ında eşleşmez → NEUTRAL fallback (karantina)
    ps = fresh_env
    state = ps.load()
    for i in range(5):
        state.recent_trades.append(
            ps.Trade(
                id=f"l{i}", symbol="BTCUSD", side="long",
                entry_price=100.0, exit_price=99.0, pnl_usd=-50.0,
                opened_at="2026-06-01T00:00:00+00:00",
                closed_at="2026-06-01T01:00:00+00:00",
                close_reason="SL_HIT", fingerprint=legacy, data_verified=True,
            )
        )
    ps.save(state)
    # Legacy fingerprint kendi içinde hâlâ AVOID üretir (geçmiş bozulmaz)
    assert mm.evaluate(legacy).action == "AVOID"
    # Ama v2 fingerprint legacy kayıtlarla eşleşmez → NEUTRAL (MIN_TRADES altı)
    v = mm.evaluate(v2)
    assert v.action == "NEUTRAL"
    assert v.size_factor == 1.0


# ---------------- thresholds timeframe_risk ----------------

def test_timeframe_risk_policy_loaded() -> None:
    from packages.data.registry.loader import load_thresholds
    tf_risk = load_thresholds()["timeframe_risk"]
    assert set(tf_risk.keys()) == {"15m", "1h", "4h", "1d", "1w"}
    # 1w: strategic — doğrudan paper execution YOK
    assert tf_risk["1w"]["paper_execution"] is False
    assert tf_risk["1w"]["risk_multiplier"] == 0.0
    # Sadece risk azaltıcı: hiçbir multiplier 1.0'ı aşamaz
    for tf, cfg in tf_risk.items():
        assert 0.0 <= cfg["risk_multiplier"] <= 1.0, tf
    # 15m scout en küçük pozitif risk
    assert tf_risk["15m"]["risk_multiplier"] <= 0.5
    assert tf_risk["15m"]["role"] == "scout"


# ---------------- decision contract ----------------

def test_trade_decision_has_timeframe_default_1d() -> None:
    from packages.decision.engine import TradeDecision
    fields = {f.name: f for f in dataclasses.fields(TradeDecision)}
    assert "timeframe" in fields
    assert fields["timeframe"].default == "1d"


def test_catalyst_impact_contract_model() -> None:
    """CatalystImpact sadece contract — motor yok; model valide olmalı."""
    from packages.data.types import CatalystImpact
    ci = CatalystImpact(
        catalyst_id="c1",
        event_type="ceasefire",
        surprise_level=0.8,
        affected_assets=["BRENT", "XAUUSD", "BTCUSD"],
        expected_half_life_minutes=2880,
        affected_timeframes=["15m", "1h", "4h"],
        timeframe_bias={"15m": "bearish", "1h": "bearish"},
    )
    assert ci.decay_curve == "exponential"
    assert ci.valid_until is None
