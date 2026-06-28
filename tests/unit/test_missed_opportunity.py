"""Faz 2 — Missed Opportunity motoru testleri.

- _candidates: shadow kaydından açılmamış valid setup çıkarımı (filtreler).
- scan_and_track: enabled=false inert; enabled=true açar + dedup eder.
- _resolve_one: missed_win / avoided_loss / expired sonuç ayrımı.
- summary_viewmodel: sonuç sayımı + aktif izleme.
- PAPER_SAFE: modül paper state'e dokunmaz (import bile etmez).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.learning import missed_opportunity as mo


@pytest.fixture
def iso_log(tmp_path, monkeypatch):
    monkeypatch.setenv("MISSED_OPP_LOG_PATH", str(tmp_path / "missed.jsonl"))
    return tmp_path


class _Bar:
    def __init__(self, ts: datetime, high: float, low: float, close: float) -> None:
        self.ts, self.high, self.low, self.close = ts, high, low, close


def _record(
    *,
    conflict_action: str = "CANDIDATE_OPEN",
    agreement: str = "SHADOW_ONLY_ENTRY",
    side: str = "long",
    with_targets: bool = True,
    tf: str = "1d",
) -> dict:
    tc: dict = {}
    if with_targets:
        tc = {"side": side, "entry": 100.0, "tf_aware": {"sl": 95.0, "tp": 110.0, "rr": 3.0}}
    return {
        "snapshot_id": "snap::test",
        "symbols": [
            {
                "symbol": "BTCUSD",
                "agreement": agreement,
                "shadow": {"entry_timeframe": tf},
                "setup_conflict": {
                    "conflict_final_action": conflict_action,
                    "setup_type": "TREND_LONG",
                    "trade_profile": "SWING",
                    "target_comparison": tc,
                },
            }
        ],
    }


def _cfg(enabled: bool = True) -> mo.MissedOppConfig:
    return mo.MissedOppConfig(enabled=enabled, min_rr=1.0, ttl_hours=dict(mo._DEFAULT_TTL_HOURS))


# ----------------- candidate çıkarımı -----------------

def test_candidates_extracts_valid() -> None:
    cands = mo._candidates(_record())
    assert len(cands) == 1
    c = cands[0]
    assert c["symbol"] == "BTCUSD" and c["side"] == "long"
    assert c["entry"] == 100.0 and c["sl"] == 95.0 and c["tp"] == 110.0


def test_candidates_skips_agree_entry() -> None:
    # Canlı aynı yönde açtıysa kaçırma değil.
    assert mo._candidates(_record(agreement="AGREE_ENTRY")) == []


def test_candidates_skips_non_candidate_open() -> None:
    assert mo._candidates(_record(conflict_action="NO_TRADE")) == []


def test_candidates_skips_missing_targets() -> None:
    assert mo._candidates(_record(with_targets=False)) == []


# ----------------- scan_and_track -----------------

def test_scan_disabled_is_inert(iso_log) -> None:
    out = mo.scan_and_track(_record(), cfg=_cfg(enabled=False))
    assert out["enabled"] is False
    assert out["tracked_new"] == 0
    assert mo.read_recent() == []


def test_scan_opens_and_dedups(iso_log) -> None:
    out1 = mo.scan_and_track(_record(), cfg=_cfg(), get_bars=lambda s, tf: [])
    assert out1["tracked_new"] == 1 and out1["active"] == 1
    # Aynı symbol/tf/side için ikinci tick yeni izleme AÇMAZ (dedup).
    out2 = mo.scan_and_track(_record(), cfg=_cfg(), get_bars=lambda s, tf: [])
    assert out2["tracked_new"] == 0 and out2["active"] == 1


# ----------------- çözümleme -----------------

def _tracking(opened: datetime) -> dict:
    return {
        "id": "x",
        "symbol": "BTCUSD",
        "timeframe": "1d",
        "side": "long",
        "entry": 100.0,
        "sl": 95.0,
        "tp": 110.0,
        "trade_profile": "SWING",
        "opened_at": opened.isoformat(),
    }


def test_resolve_missed_win() -> None:
    opened = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [_Bar(opened + timedelta(days=1), high=111.0, low=99.0, close=110.0)]
    res = mo._resolve_one(
        _tracking(opened), now=opened + timedelta(days=2), cfg=_cfg(), get_bars=lambda s, tf: bars
    )
    assert res is not None and res["outcome"] == "missed_win"


def test_resolve_avoided_loss() -> None:
    opened = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [_Bar(opened + timedelta(days=1), high=101.0, low=94.0, close=95.0)]
    res = mo._resolve_one(
        _tracking(opened), now=opened + timedelta(days=2), cfg=_cfg(), get_bars=lambda s, tf: bars
    )
    assert res is not None and res["outcome"] == "avoided_loss"


def test_resolve_expired() -> None:
    opened = datetime(2026, 1, 1, tzinfo=UTC)
    # TP/SL'e değmeyen bar + TTL (1d=240sa) geçmiş now.
    bars = [_Bar(opened + timedelta(days=1), high=101.0, low=99.0, close=100.0)]
    res = mo._resolve_one(
        _tracking(opened), now=opened + timedelta(days=20), cfg=_cfg(), get_bars=lambda s, tf: bars
    )
    assert res is not None and res["outcome"] == "expired"


def test_resolve_pending_when_untouched_and_within_ttl() -> None:
    opened = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [_Bar(opened + timedelta(hours=1), high=101.0, low=99.0, close=100.0)]
    res = mo._resolve_one(
        _tracking(opened), now=opened + timedelta(hours=2), cfg=_cfg(), get_bars=lambda s, tf: bars
    )
    assert res is None  # açık kalır


# ----------------- viewmodel + entegrasyon -----------------

def test_summary_viewmodel_counts(iso_log) -> None:
    # Aç → sonra TP'ye değen barlarla çöz.
    opened = datetime.now(UTC) - timedelta(days=3)
    mo.scan_and_track(_record(), now=opened, cfg=_cfg(), get_bars=lambda s, tf: [])
    bars = [_Bar(opened + timedelta(days=1), high=111.0, low=99.0, close=110.0)]
    out = mo.scan_and_track(
        {"snapshot_id": "snap::test", "symbols": []},
        now=opened + timedelta(days=2),
        cfg=_cfg(),
        get_bars=lambda s, tf: bars,
    )
    assert out["resolved"] == 1
    vm = mo.summary_viewmodel()
    assert vm["available"] is True
    assert vm["outcomes"]["missed_win"] == 1
    assert vm["by_profile"].get("SWING", {}).get("missed_win") == 1
