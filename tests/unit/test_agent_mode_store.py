"""Faz 3 — Agent Mode override store + config merge testleri.

- sanitize: yalnızca bilinen anahtarlar; geçersiz profil/anahtar reddedilir.
- save/load roundtrip + clear.
- load_config: store boşsa thresholds defaults birebir korunur (bozulmama);
  store doluysa override defaults'un üstüne uygulanır.
- endpoint GET/POST/reset (in-process) ana thresholds dosyasına dokunmaz.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def iso_store(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MODE_STORE_PATH", str(tmp_path / "agent_mode.json"))
    return tmp_path


# ----------------- sanitize -----------------

def test_sanitize_keeps_known_rejects_unknown() -> None:
    from packages.mode import store
    clean = store.sanitize(
        {
            "disabled_trade_profiles": ["SCALP", "BOGUS", "SWING"],
            "allow_reversal_trades": False,
            "unknown_key": 123,
            "focus_mode": "INTRADAY",
        }
    )
    assert clean["disabled_trade_profiles"] == ["SCALP", "SWING"]  # BOGUS düştü
    assert clean["allow_reversal_trades"] is False
    assert clean["focus_mode"] == "INTRADAY"
    assert "unknown_key" not in clean


def test_sanitize_invalid_focus_mode_becomes_none() -> None:
    from packages.mode import store
    assert store.sanitize({"focus_mode": "NOPE"})["focus_mode"] is None


# ----------------- store roundtrip -----------------

def test_save_load_clear_roundtrip(iso_store) -> None:
    from packages.mode import store
    assert store.load_overrides() == {}
    store.save_overrides({"disabled_trade_profiles": ["SCALP"], "allow_range_trades": False})
    loaded = store.load_overrides()
    assert loaded["disabled_trade_profiles"] == ["SCALP"]
    assert loaded["allow_range_trades"] is False
    store.clear()
    assert store.load_overrides() == {}


# ----------------- config merge (bozulmama) -----------------

def test_load_config_empty_store_preserves_defaults(iso_store) -> None:
    from packages.mode import config
    cfg = config.load_config()
    # thresholds_v1.0.yaml agent_mode_control defaults: hiçbir şey kısıtlamaz.
    assert cfg.disabled_trade_profiles == ()
    assert cfg.allow_reversal_trades is True
    assert cfg.allow_trend_follow_trades is True


def test_load_config_applies_override(iso_store) -> None:
    from packages.mode import config, store
    store.save_overrides({"disabled_trade_profiles": ["SCALP"], "allow_reversal_trades": False})
    cfg = config.load_config()
    assert "SCALP" in cfg.disabled_trade_profiles
    assert cfg.allow_reversal_trades is False
    # Override edilmeyen alan default kalır.
    assert cfg.allow_breakout_trades is True


def test_override_changes_filter_outcome(iso_store) -> None:
    from packages.mode import config, store
    from packages.mode import filter as mode_filter
    # SCALP disabled → SCALP_LONG setup'ı SCALP profilinde bloklanır.
    store.save_overrides({"disabled_trade_profiles": ["SCALP"]})
    cfg = config.load_config()
    res = mode_filter.evaluate(
        setup_type="SCALP_LONG", trade_profile="SCALP", is_countertrend=False, cfg=cfg
    )
    assert res.passed is False
    assert "SCALP" in (res.blocked_reason or "")


# ----------------- endpoint (in-process) -----------------

def test_endpoints_roundtrip(iso_store, monkeypatch) -> None:
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    from fastapi.testclient import TestClient

    from apps.api.main import app
    c = TestClient(app)

    g = c.get("/api/v1/agent-mode/config")
    assert g.status_code == 200
    assert g.json()["config"]["disabled_trade_profiles"] == []

    p = c.post(
        "/api/v1/agent-mode/config",
        json={"disabled_trade_profiles": ["SCALP", "BOGUS"], "bogus": 1},
    )
    assert p.status_code == 200
    body = p.json()
    assert body["config"]["disabled_trade_profiles"] == ["SCALP"]  # BOGUS reddedildi
    assert "bogus" not in body["overrides"]

    r = c.post("/api/v1/agent-mode/config/reset")
    assert r.status_code == 200
    assert r.json()["config"]["disabled_trade_profiles"] == []
