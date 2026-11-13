"""Piyasa şoku bildirimi: ölçü, tetik, soğuma, metin ve çalışma zamanı yapıştırıcısı."""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.notifications import market_shock as ms

NOW = datetime(2026, 11, 13, 3, 20, tzinfo=UTC)
LAST_BAR = datetime(2026, 11, 13, 2, 0, tzinfo=UTC)  # 03:00'te kapanmış son tamamlanmış bar


def _series(n: int = 200, last_jump: float = 0.0) -> list[float]:
    """Küçük, deterministik dalgalanma (σ ≈ %0,3) + son barda isteğe bağlı sıçrama."""
    closes = [100.0]
    for i in range(1, n):
        closes.append(closes[-1] * math.exp(0.003 * (1 if i % 2 else -1)))
    closes[-1] = closes[-2] * (1 + last_jump)
    return closes


def _move(sym: str, cls: str, z: float, ts: float = 0.0) -> ms.Move:
    return ms.Move(sym, cls, ts, z, 1, z * 0.3)


def test_score_scales_by_own_volatility_and_excludes_last_bar_from_sigma() -> None:
    quiet = ms.score(_series())
    assert quiet is not None and abs(quiet[0]) < 2
    z, hours, pct = ms.score(_series(last_jump=-0.03))
    assert z < -5 and hours == 1 and pct == pytest.approx(-3.0, abs=0.01)
    assert ms.score(_series(n=40)) is None  # σ için yetersiz geçmiş


def test_sigma_is_the_previous_168_returns_not_including_the_shock_bar() -> None:
    import statistics

    closes = _series(last_jump=-0.03)
    rets = [math.log(closes[k + 1] / closes[k]) for k in range(len(closes) - 1)]
    expected = math.log(closes[-1] / closes[-2]) / statistics.stdev(rets[-169:-1])
    z, hours, _ = ms.score(closes)
    assert hours == 1 and z == pytest.approx(expected, rel=1e-9)


def test_score_picks_the_horizon_with_the_largest_scaled_move() -> None:
    closes = _series()
    for k in range(6):  # son 6 bar her biri %0,6 düşüş: tek bar küçük, 6 saatlik toplam büyük
        closes[-6 + k] = closes[-7 + k] * 0.994
    z, hours, _ = ms.score(closes)
    assert hours in (3, 6) and z < -2.5


def test_cross_needs_four_symbols_from_two_classes() -> None:
    same_class = [_move(s, "crypto", -3.0) for s in ("A", "B", "C", "D")]
    assert ms.scan(same_class, {}) == []
    mixed = [*same_class[:3], _move("E", "energy", 3.0)]
    fired = ms.scan(mixed, {})
    assert len(fired) == 1 and fired[0][0] == "çapraz" and len(fired[0][1]) == 4


def test_single_symbol_needs_five_sigma_and_cooldown_blocks_repeat() -> None:
    assert ms.scan([_move("ETHUSD", "crypto", -4.9)], {}) == []
    fired = ms.scan([_move("ETHUSD", "crypto", -5.1, ts=10_000.0)], {})
    assert fired[0][0] == "tek"
    assert ms.scan([_move("ETHUSD", "crypto", -6.0, ts=10_000.0 + 5 * 3600)], {"ETHUSD": 10_000.0}) == []
    assert ms.scan([_move("ETHUSD", "crypto", -6.0, ts=10_000.0 + 6 * 3600)], {"ETHUSD": 10_000.0})


def test_symbols_are_grouped_by_their_own_bar_time() -> None:
    # Hisse barları :30'da, kripto :00'da: farklı zamanlı barlar tek "çapraz" sayılmaz.
    moves = [_move("A", "crypto", 3.0, 0.0), _move("B", "crypto", 3.0, 0.0),
             _move("X", "equity", 3.0, 1800.0), _move("Y", "risk", 3.0, 1800.0)]
    assert ms.scan(moves, {}) == []


def test_message_tells_what_happened_who_is_hit_and_what_the_system_sees() -> None:
    chosen = [ms.Move("ETHUSD", "crypto", LAST_BAR.timestamp(), -5.1, 1, -2.78)]
    n = ms.build(
        "tek", chosen, NOW,
        headlines=[{"ts": (NOW - timedelta(minutes=40)).isoformat(), "title": "Ether slides as liquidations mount",
                    "source": "CoinDesk", "symbols": {"ETHUSD": -1.0}},
                   {"ts": (NOW - timedelta(hours=5)).isoformat(), "title": "eski başlık", "symbols": {"ETHUSD": -1.0}}],
        positions=[{"symbol": "ETHUSD", "side": "long", "timeframe": "1h"}],
        cells=[{"symbol": "ETHUSD", "timeframe": "1h", "candidate": "open_short", "action": "hold",
                "blocked_by": ["entry_quality_v2:reduce", "ev_gate"]}],
        risk_action="WATCH",
    )
    assert n.type == "event_outcome" and n.priority == "critical"  # açık pozisyon harekete ters
    assert "ETHUSD −%2,8" in n.title
    assert "yön aşağı" in n.body_long and "kripto" in n.body_long
    assert "Ether slides" in n.body_long and "eski başlık" not in n.body_long
    assert "ETHUSD 1h long (ALEYHTE)" in n.body_long
    assert "ETHUSD 1h: short adayı, engel: beklenen değer kapısı" in n.body_long
    assert "Risk seviyesi: izleme" in n.body_long
    assert "işlem önerisi değildir" in n.body_long


def test_message_without_headlines_or_positions_says_so() -> None:
    n = ms.build("tek", [ms.Move("DODO", "crypto", LAST_BAR.timestamp(), 6.0, 3, 15.3)], NOW)
    assert n.priority == "high"
    assert "başlık yok" in n.body_long and "bu sembollerde yok" in n.body_long


def _write_cache(root, sym: str, closes: list[float], last: datetime) -> None:
    start = last - timedelta(hours=len(closes) - 1)
    bars = [{"symbol": sym, "timeframe": "1h", "ts": (start + timedelta(hours=i)).isoformat(), "open": c,
             "high": c, "low": c, "close": c, "source": "test", "verified": True} for i, c in enumerate(closes)]
    (root / f"{sym}_1h.json").write_text(json.dumps({"symbol": sym, "timeframe": "1h",
                                                    "fetched_at": NOW.isoformat(), "bars": bars}), encoding="utf-8")


def test_check_reads_completed_bars_notifies_once_and_skips_stale_symbols(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / "ohlcv"
    cache_dir.mkdir()
    monkeypatch.setenv("OHLCV_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("MARKET_SHOCK_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("DECISION_RECORD_DIR", str(tmp_path / "rec"))
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "ps.json"))
    monkeypatch.setenv("NEWS_EVENT_LEDGER_PATH", str(tmp_path / "news.jsonl"))
    classes = {"BTCUSD": "crypto", "ETHUSD": "crypto", "BRENT": "energy", "XAUUSD": "precious_metal", "NVDA": "risk"}
    monkeypatch.setattr("packages.data.registry.assets.trade_symbols", lambda: list(classes))
    monkeypatch.setattr("packages.data.registry.assets.get", lambda s: SimpleNamespace(asset_class=classes[s]))
    for sym in ("BTCUSD", "ETHUSD", "XAUUSD"):
        _write_cache(cache_dir, sym, _series(last_jump=-0.012), LAST_BAR)
    _write_cache(cache_dir, "BRENT", _series(last_jump=0.012), LAST_BAR)
    # Henüz kapanmamış 03:00 barı (sıçramalı) sayılmamalı; NVDA'nın verisi bayat (piyasa kapalı).
    eth = json.loads((cache_dir / "ETHUSD_1h.json").read_text(encoding="utf-8"))
    eth["bars"].append({**eth["bars"][-1], "ts": (LAST_BAR + timedelta(hours=1)).isoformat(), "close": 50.0})
    (cache_dir / "ETHUSD_1h.json").write_text(json.dumps(eth), encoding="utf-8")
    _write_cache(cache_dir, "NVDA", _series(last_jump=-0.05), LAST_BAR - timedelta(hours=10))
    # Karar kaydı: tam liste checkpoint'te, sonraki delta satırlarında ETH yok → görüş checkpoint'ten gelmeli.
    rec = tmp_path / "rec"
    rec.mkdir()
    eth_cell = {"symbol": "ETHUSD", "timeframe": "1h", "candidate": "open_short", "action": "hold", "blocked_by": ["ev_gate"]}
    old_btc = {"symbol": "BTCUSD", "timeframe": "1h", "candidate": "open_long", "action": "hold", "blocked_by": ["confidence_floor"]}
    new_btc = {"symbol": "BTCUSD", "timeframe": "1h", "candidate": "hold", "action": "hold", "blocked_by": []}
    lines = [{"kind": "checkpoint", "risk_action": "WATCH", "cells": [eth_cell, old_btc]},
             {"kind": "delta", "risk_action": "WATCH", "cells": [new_btc]},
             {"kind": "delta", "risk_action": "HOLD", "cells": []}]
    (rec / "2026-11-13.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")

    first = ms.check(NOW)
    assert len(first) == 1
    n = first[0]
    assert "Sert hareket" in n.title and "NVDA" not in n.body_long
    assert "ETHUSD −%1,2 (1 sa" in n.body_long  # kapanmamış 03:00 barı (−%50) sayılmadı
    assert "ETHUSD 1h: short adayı, engel: beklenen değer kapısı" in n.body_long
    assert "BTCUSD 1h: aday yok" in n.body_long  # en yeni delta checkpoint'teki eski hücreyi ezer
    assert "Risk seviyesi: normal (kapı açık)" in n.body_long  # HOLD = risk motorunda en serbest seviye
    assert "birden çok varlık" in n.body_long and "yön karışık" in n.body_long
    assert ms.check(NOW) == []  # aynı bar, soğuma dosyada
    assert ms.check(NOW + timedelta(minutes=5)) == []
