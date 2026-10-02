"""H10 — rejim hysteresis hafızasının tek yazarı tick worker; GET'ler yazmaz."""
from __future__ import annotations

import json
from types import SimpleNamespace

from packages.data.registry.loader import threshold_override
from packages.regime import classifier as rc


def _snap(dxy=104.0, us10=4.3):
    q = lambda s, p: SimpleNamespace(symbol=s, price=p)  # noqa: E731
    return SimpleNamespace(
        prices=[q("DXY", dxy), q("US10Y", us10), q("US02Y", 4.3), q("VIX", 18.0), q("BTCUSD", 60000.0)],
        technicals={"BTCUSD": SimpleNamespace(
            direction_score=55.0, status="OK", score=55.0, rsi=55.0, ema_stack="mixed",
        )},
        rotation=SimpleNamespace(score=55.0, direction="neutral", evidence=[], status="OK"),
    )


def test_read_only_classify_uses_memory_but_never_writes(tmp_path, monkeypatch):
    p = tmp_path / "regime_state.json"
    monkeypatch.setenv("REGIME_STATE_PATH", str(p))
    with threshold_override({"regime": {"hysteresis_band": 3.0}}):
        written = rc.classify(_snap(), persist=True)      # tick: hafızayı kurar
        before = p.read_text(encoding="utf-8")
        p.write_text(json.dumps({"label": "CRISIS"}), encoding="utf-8")
        read_only = rc.classify(_snap())                   # GET: okur, yazmaz
    assert p.read_text(encoding="utf-8") == json.dumps({"label": "CRISIS"})
    assert json.loads(before)["label"] == written.label
    # Okuma yolu da aynı hafızayı kullanır (worker'ın gösterdiği etiketle tutarlı).
    assert read_only.raw_label is not None


def test_decide_matrix_default_does_not_persist(monkeypatch):
    from packages.decision import engine

    seen = {}

    def fake_classify(snap, **kw):
        seen.update(kw)
        raise RuntimeError("stop")

    monkeypatch.setattr(engine, "classify", fake_classify)
    for kwargs, expected in (({}, False), ({"persist_regime": True}, True)):
        seen.clear()
        try:
            engine.decide_matrix(["BTCUSD"], SimpleNamespace(), SimpleNamespace(), **kwargs)
        except RuntimeError:
            pass
        assert seen == {"persist": expected}
