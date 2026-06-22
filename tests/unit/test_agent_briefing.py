"""Raporcu agent briefing — yönetici özeti + motor tazeliği sözleşmesi.

LLM yok; tamamen deterministik. Bu testler shape'i ve bayat-motor uyarısının
en üste çıkışını kilitler (observer; karar vermez).
"""
from __future__ import annotations

from packages.agent import briefing


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
