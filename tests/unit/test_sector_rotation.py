"""K-0b — sektör rotasyon motoru testleri (owner kararı 2026-07-04).

Ağa ÇIKMAZ: get_bars stub'lanır. Kapsam: hüküm hesabı (göreli güç),
UNAVAILABLE dürüstlüğü, sıralama, karne damga/çözüm döngüsü, cadence
cache'i ve flag-OFF bekçisi (learning koşusu bayt-eşdeğer).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packages import discovery
from packages.data.types import OHLCVBar
from packages.discovery import sector_rotation as sr


def _bars(symbol: str, closes: list[float], *, verified: bool = True) -> list[OHLCVBar]:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCVBar(
            symbol=symbol, timeframe="1d", ts=t0 + timedelta(days=i),
            open=c, high=c, low=c, close=c, source="test", verified=verified,
        )
        for i, c in enumerate(closes)
    ]


def _flat(n: int = 70, level: float = 100.0) -> list[float]:
    return [level] * n


def _trending(n: int = 70, start: float = 100.0, daily_pct: float = 0.005) -> list[float]:
    out, c = [], start
    for _ in range(n):
        out.append(c)
        c *= 1 + daily_pct
    return out


def _cfg(sectors: dict[str, dict] | None = None, **over) -> dict:
    cfg = {
        "benchmark": "SP500",
        "interval_sec": 3600,
        "verdict_threshold_pct": 1.0,
        "resolve_after_days": 7,
        "pending_max_age_days": 30,
        "sectors": sectors or {"XLK": {"label": "Teknoloji"}, "XLE": {"label": "Enerji"}},
    }
    cfg.update(over)
    return cfg


def test_rising_falling_neutral_and_rank():
    data = {
        "SP500": _bars("SP500", _flat()),
        "XLK": _bars("XLK", _trending(daily_pct=0.005)),    # bench'i ezer → RISING
        "XLE": _bars("XLE", _trending(daily_pct=-0.005)),   # bench altında → FALLING
        "XLF": _bars("XLF", _flat(level=50.0)),             # bench'le aynı → NEUTRAL
    }
    cfg = _cfg({"XLK": {"label": "Tek"}, "XLE": {"label": "Enerji"}, "XLF": {"label": "Finans"}})
    ev = sr.evaluate(cfg, get_bars=lambda s, tf: data[s])
    by = {s["sector"]: s for s in ev["sectors"]}
    assert by["XLK"]["verdict"] == "RISING" and by["XLK"]["score"] > 0
    assert by["XLE"]["verdict"] == "FALLING" and by["XLE"]["score"] < 0
    assert by["XLF"]["verdict"] == "NEUTRAL"
    # sıralama: en güçlü 1
    assert by["XLK"]["rank"] == 1 and by["XLE"]["rank"] == 3
    assert by["XLK"]["last_close"] == pytest.approx(_trending(daily_pct=0.005)[-1])


def test_insufficient_or_unverified_bars_unavailable():
    data = {
        "SP500": _bars("SP500", _flat()),
        "XLK": _bars("XLK", _flat(n=10)),                      # az bar
        "XLE": _bars("XLE", _flat(), verified=False),          # doğrulanmamış
    }
    ev = sr.evaluate(_cfg(), get_bars=lambda s, tf: data[s])
    by = {s["sector"]: s for s in ev["sectors"]}
    for sym in ("XLK", "XLE"):
        assert by[sym]["verdict"] == "UNAVAILABLE"
        assert by[sym]["score"] is None and by[sym]["rank"] is None


def test_benchmark_missing_all_unavailable():
    data = {
        "SP500": [],
        "XLK": _bars("XLK", _trending()),
        "XLE": _bars("XLE", _trending()),
    }
    ev = sr.evaluate(_cfg(), get_bars=lambda s, tf: data[s])
    assert ev["benchmark_ok"] is False
    assert all(s["verdict"] == "UNAVAILABLE" for s in ev["sectors"])


def _patch_cfg(monkeypatch, cfg):
    monkeypatch.setattr(sr, "load_config", lambda: cfg)


def test_run_stamps_once_per_day_and_caches(monkeypatch, tmp_path):
    monkeypatch.setenv("SECTOR_ROTATION_PATH", str(tmp_path / "sector.json"))
    data = {
        "SP500": _bars("SP500", _flat()),
        "XLK": _bars("XLK", _trending(daily_pct=0.005)),
        "XLE": _bars("XLE", _trending(daily_pct=-0.005)),
    }
    _patch_cfg(monkeypatch, _cfg())
    now = datetime(2026, 7, 4, 10, 0, tzinfo=UTC)

    r1 = sr.run_if_due(now=now, get_bars=lambda s, tf: data[s])
    assert r1["status"] == "OK"
    assert r1["stamped"] == 2 and r1["rising"] == ["XLK"]

    # interval dolmadan → CACHED (ağa/hesaba girmez)
    calls = {"n": 0}

    def counting(s, tf):
        calls["n"] += 1
        return data[s]

    r2 = sr.run_if_due(now=now + timedelta(minutes=10), get_bars=counting)
    assert r2["status"] == "CACHED" and calls["n"] == 0

    # interval doldu ama AYNI gün → yeniden damga YOK
    r3 = sr.run_if_due(now=now + timedelta(hours=2), get_bars=lambda s, tf: data[s])
    assert r3["status"] == "OK" and r3["stamped"] == 0

    art = json.loads(Path(os.environ["SECTOR_ROTATION_PATH"]).read_text(encoding="utf-8"))
    assert art["last_stamp_date"] == "2026-07-04"
    assert len(art["scorecard"]["pending"]) == 2


def test_scorecard_resolves_with_realized_relative_return(monkeypatch, tmp_path):
    monkeypatch.setenv("SECTOR_ROTATION_PATH", str(tmp_path / "sector.json"))
    _patch_cfg(monkeypatch, _cfg())
    day1 = datetime(2026, 7, 4, 10, 0, tzinfo=UTC)

    data1 = {
        "SP500": _bars("SP500", _flat()),
        "XLK": _bars("XLK", _trending(daily_pct=0.005)),   # RISING damgalanır
        "XLE": _bars("XLE", _trending(daily_pct=-0.005)),  # FALLING damgalanır
    }
    assert sr.run_if_due(now=day1, get_bars=lambda s, tf: data1[s])["stamped"] == 2

    # 8 gün sonra: XLK bench'i GERÇEKTEN geçti (RISING doğru),
    # XLE bench'in ÜSTÜNE çıktı (FALLING yanlış).
    xlk_last = _trending(daily_pct=0.005)[-1]
    xle_last = _trending(daily_pct=-0.005)[-1]
    data2 = {
        "SP500": _bars("SP500", _flat()),                          # bench sabit
        "XLK": _bars("XLK", _flat(level=xlk_last * 1.05)),          # +%5
        "XLE": _bars("XLE", _flat(level=xle_last * 1.05)),          # +%5 (ters yönde)
    }
    r = sr.run_if_due(now=day1 + timedelta(days=8), get_bars=lambda s, tf: data2[s])
    # 2 damga çözüldü; 2. gün verisi düz seyir → hükümler NEUTRAL, yeni damga yok
    assert r["resolved_new"] == 2 and r["pending_n"] == 0

    art = json.loads(Path(os.environ["SECTOR_ROTATION_PATH"]).read_text(encoding="utf-8"))
    resolved = {x["sector"]: x for x in art["scorecard"]["resolved"]}
    assert resolved["XLK"]["correct"] is True and resolved["XLK"]["realized_rel_pct"] > 0
    assert resolved["XLE"]["correct"] is False
    assert art["scorecard"]["overall"] == {"resolved_n": 2, "correct_n": 1, "hit_rate": 0.5}


def test_pending_expires_after_max_age(monkeypatch, tmp_path):
    monkeypatch.setenv("SECTOR_ROTATION_PATH", str(tmp_path / "sector.json"))
    _patch_cfg(monkeypatch, _cfg())
    day1 = datetime(2026, 7, 4, 10, 0, tzinfo=UTC)
    data = {
        "SP500": _bars("SP500", _flat()),
        "XLK": _bars("XLK", _trending(daily_pct=0.005)),
        "XLE": _bars("XLE", _flat(level=50.0)),
    }
    sr.run_if_due(now=day1, get_bars=lambda s, tf: data[s])
    # 40 gün sonra: veri artık UNAVAILABLE (çözülemez) → damga düşer, karne dürüst
    data_gone = {"SP500": [], "XLK": [], "XLE": []}
    sr.run_if_due(now=day1 + timedelta(days=40), get_bars=lambda s, tf: data_gone[s])
    art = json.loads(Path(os.environ["SECTOR_ROTATION_PATH"]).read_text(encoding="utf-8"))
    assert art["scorecard"]["expired_total"] == 1
    assert art["scorecard"]["pending"] == [] and art["scorecard"]["resolved"] == []


def test_flag_off_worker_step_is_noop(monkeypatch, tmp_path):
    # OFF bekçisi: flag kapalıyken (conftest delenv) hiçbir dosya yazılmaz,
    # motor hiç çağrılmaz — learning koşusu bayt-eşdeğer.
    out = tmp_path / "sector.json"
    monkeypatch.setenv("SECTOR_ROTATION_PATH", str(out))
    assert discovery.scan_enabled() is False

    def boom(*a, **k):  # motor çağrılırsa test patlasın
        raise AssertionError("sector_rotation flag OFF iken çağrıldı")

    monkeypatch.setattr(sr, "run_if_due", boom)
    if discovery.scan_enabled():  # worker'daki guard'ın birebir kopyası
        sr.run_if_due()
    assert not out.exists()


def test_flag_on_via_env(monkeypatch):
    monkeypatch.setenv("DISCOVERY_SCAN_ENABLED", "1")
    assert discovery.scan_enabled() is True
    monkeypatch.setenv("DISCOVERY_SCAN_ENABLED", "off")
    assert discovery.scan_enabled() is False


def test_live_config_loads_12_sectors():
    cfg = sr.load_config()
    sectors = cfg.get("sectors") or {}
    assert len(sectors) == 12
    assert set(sectors) >= {"XLK", "XLE", "IYT", "XLRE"}
    assert cfg.get("benchmark") == "SP500"
