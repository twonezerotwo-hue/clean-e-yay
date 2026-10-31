"""Açıklama paketi: yönü iten / karşı duran modüller, ilk engel, rota ve özet."""
from __future__ import annotations

from types import SimpleNamespace

from packages.decision import explain


def _decision(direction="bullish", score=63.0, action="hold", blocked=("ev_gate",)):
    mods = [
        SimpleNamespace(name="touche", layer="vote", score=80.0, weight=0.4),       # +12.0
        SimpleNamespace(name="fundamental", layer="context", score=40.0, weight=0.3),  # −3.0
        SimpleNamespace(name="sentinel", layer="context", score=60.0, weight=0.2),  # +2.0
        SimpleNamespace(name="news", layer="vote", score=50.0, weight=0.1),         # 0
    ]
    cons = SimpleNamespace(direction=direction, score=score, modules=mods)
    return SimpleNamespace(consensus=cons, action=action, blocked_by=list(blocked))


def test_drivers_and_against_follow_direction():
    pkg = explain.build(_decision(), SimpleNamespace(route="block"))
    assert [m["module"] for m in pkg["drivers"]] == ["touche", "sentinel"]
    assert [m["module"] for m in pkg["against"]] == ["fundamental"]
    assert pkg["drivers"][0]["lean"] == 12.0 and pkg["against"][0]["lean"] == -3.0
    assert pkg["blocker"] == "ev_gate" and pkg["route"] == "block"
    assert pkg["why_now"] == (
        "yükseliş 63.0 — iten: teknik +12.0, risk iştahı +2.0 — karşı: temel −3.0 — bekle (ev_gate) · rota block"
    )


def test_bearish_flips_roles_and_neutral_has_no_drivers():
    bear = explain.build(_decision(direction="bearish", score=40.0, action="open_short", blocked=()))
    assert [m["module"] for m in bear["drivers"]] == ["fundamental"]
    assert bear["blocker"] is None and bear["why_now"].endswith("short aç")
    neutral = explain.build(_decision(direction="neutral", score=50.0))
    assert neutral["drivers"] == [] and neutral["against"] == []
