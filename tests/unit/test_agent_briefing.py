"""Raporcu agent briefing — yönetici özeti + motor tazeliği sözleşmesi.

LLM yok; tamamen deterministik. Bu testler shape'i ve bayat-motor uyarısının
en üste çıkışını kilitler (observer; karar vermez).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from packages.agent import briefing


def test_bearish_score_is_reported_as_directional_strength():
    assert briefing._directional_strength({"score": 35, "direction": "bearish"}) == 65
    assert briefing._directional_strength({"score": 65, "direction": "bullish"}) == 65


def test_build_shape():
    out = briefing.build()
    assert {"generated_at", "headlines", "executive", "engine", "stale", "dqs"} <= out.keys()

    eng = out["engine"]
    assert {"status", "age_seconds", "cycle_count", "stale"} <= eng.keys()
    assert isinstance(eng["stale"], bool)
    assert out["stale"] == eng["stale"]

    exe = out["executive"]
    assert exe["stance"] in {
        "halt", "stale", "blocked", "data_gap", "signal", "watching", "calm"
    }
    assert exe["tone"] in {"ok", "info", "warn", "alert"}
    for key in ("headline", "narrative", "recommendation", "stance_label"):
        assert isinstance(exe[key], str) and exe[key].strip()
    assert isinstance(exe["flags"], list)
    assert len(exe["flags"]) <= 4


def test_headlines_sorted_by_severity():
    """Genel müdür önce sorunu söyler: alert/warn, info'dan önce gelir."""
    rank = {"alert": 0, "warn": 1, "info": 2, "ok": 3}
    ranks = [rank[h["tone"]] for h in briefing.build()["headlines"]]
    assert ranks == sorted(ranks)


def test_stale_engine_drives_stance_and_flag(monkeypatch):
    """Motor bayatsa duruş 'stale' olur, headline ve flag bunu öne çıkarır."""
    monkeypatch.setattr(
        briefing,
        "_engine_health",
        lambda: {
            "status": "DEGRADED",
            "age_seconds": 11000.0,
            "cycle_count": 7,
            "stale": True,
        },
    )
    out = briefing.build()
    assert out["stale"] is True
    # Halt yoksa stale en yüksek öncelikli duruştur.
    if out["executive"]["stance"] != "halt":
        assert out["executive"]["stance"] == "stale"
        assert out["executive"]["tone"] == "alert"
        assert any("motor" in f.lower() for f in out["executive"]["flags"])


def test_fmt_age():
    assert briefing._fmt_age(None) == "bilinmiyor"
    assert briefing._fmt_age(45).endswith("sn")
    assert briefing._fmt_age(600).endswith("dk")
    assert briefing._fmt_age(11000).endswith("sa")


def test_signal_briefing_distinguishes_paper_from_live_execution(monkeypatch):
    """Paper otomatik açılış ile gerçek broker emrini birbirine karıştırmaz."""
    snap = SimpleNamespace(
        quality=SimpleNamespace(score=90.0, status="OK"),
        provider_status={},
    )
    monkeypatch.setattr(briefing, "get_cached_snapshot", lambda: snap)
    monkeypatch.setattr(briefing, "classify", lambda _snap: SimpleNamespace(label="NEUTRAL"))
    monkeypatch.setattr(briefing, "_safe_cells", lambda _snap, paper_state_obj=None: [{
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "direction": "LONG",
        "score": 60.0,
    }])
    monkeypatch.setattr(
        briefing,
        "_engine_health",
        lambda: {"status": "OK", "age_seconds": 1.0, "cycle_count": 1, "stale": False},
    )
    monkeypatch.setattr(briefing.halt_store, "active_halts", lambda: [])
    monkeypatch.setattr(briefing.paper_state, "load", lambda: SimpleNamespace(open_positions=[]))
    monkeypatch.setattr(briefing, "_nearest_event", lambda _snap: None)

    out = briefing.build()["executive"]
    if out["stance"] == "signal":
        text = out["recommendation"].lower()
        assert "paper_only" in text
        assert "gerçek broker emri gönderilmez" in text
        assert "otomatik açılır" not in text


def test_blocked_score_is_not_reported_as_trade_signal(monkeypatch):
    """Skor eşiği geçse bile final kapı blokluyorsa brief sinyal demez."""
    snap = SimpleNamespace(
        quality=SimpleNamespace(score=90.0, status="OK"),
        provider_status={},
        headlines=[],
        catalysts=[],
    )
    position = SimpleNamespace(
        id="p1",
        symbol="XAGUSD",
        side="short",
        timeframe="1h",
        size_usd=100.0,
        unrealized_pnl_usd=-0.5,
    )
    ps = SimpleNamespace(
        revision=7,
        open_positions=[position],
        last_rechecks=[{
            "position_id": "p1",
            "verdict": "WATCH",
        }],
    )
    cells = [{
        "symbol": "XAGUSD",
        "timeframe": "4h",
        "direction": "bearish",
        # Bearish scores are directional: 40 raw = 60-point short strength.
        "score": 40.0,
        "action": "hold",
        "actionable": False,
        "paper_action": "none",
        "blocked_by": ["concentration_guard"],
        "reason": "aynı sembolde açık pozisyon var",
    }]
    monkeypatch.setattr(briefing, "get_cached_snapshot", lambda: snap)
    monkeypatch.setattr(briefing, "classify", lambda _snap: SimpleNamespace(label="DEFENSIVE"))
    monkeypatch.setattr(briefing, "_safe_cells", lambda _snap, paper_state_obj=None: cells)
    monkeypatch.setattr(briefing, "_safe_world_state", lambda _snap: None)
    monkeypatch.setattr(
        briefing,
        "_engine_health",
        lambda: {"status": "OK", "age_seconds": 1.0, "cycle_count": 1, "stale": False},
    )
    monkeypatch.setattr(briefing.halt_store, "active_halts", lambda: [])
    monkeypatch.setattr(briefing.paper_state, "load", lambda: ps)
    monkeypatch.setattr(briefing, "_nearest_event", lambda _snap: None)

    executive = briefing.build()["executive"]
    assert executive["stance"] == "watching"
    assert "İşlem sinyali oluştu" not in executive["headline"]
    # Brief artık kullanıcıya Türkçe yön gösterir; backend kodu (SHORT) ham
    # biçimde anlatıya sızmamalı.
    assert "Gümüş satış" in executive["narrative"]
    assert "izlemede" in executive["narrative"]


def test_layer0_context_uses_current_news_and_world_evidence():
    """Layer-0 sabit durum cümlesi yerine güncel haber → etki → fikir zincirini gösterir."""
    now = datetime.now(UTC)
    snap = SimpleNamespace(headlines=[SimpleNamespace(
        ts=now - timedelta(minutes=5),
        source="Reuters",
        title="Trump announces new sanctions on Russia",
        title_tr="Trump Rusya'ya yeni yaptırımlar açıkladı",
        asset_impact={"XAUUSD": 1.0},
    )])
    world = SimpleNamespace(
        geopolitical_events=(SimpleNamespace(
            expired=False,
            channels=("sanctions_pressure", "trade_risk"),
            event_type="SANCTIONS",
            actors=(),
        ),),
        sanctions_pressure=0.62,
        trade_risk=0.41,
        energy_supply_risk=None,
        shipping_risk=None,
        risk_aversion=None,
        statements=(),
        asset_discovery={"candidates": [{"symbol": "XAUUSD"}]},
    )

    text = briefing._headline_world_context(snap, world)

    assert "Bugünün gündemi" in text
    assert "Piyasa etkisi" in text
    assert "yaptırım/finans baskısı artıyor" in text
    assert "Altın üzerinde yukarı haber baskısı" in text
    assert "Trump / ABD" in text
    assert "XAUUSD" in text
