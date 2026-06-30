"""CP3 — yön güvenlik kasası (guard_safety) + kill-switch (guard_overrides) testleri.

Kapsam:
  * guard_overrides: default passthrough, set/clear, mtime-cache yazımda geçersiz.
  * engine/timeframe seam'leri: override YALNIZ canlı guard'ı OFF'a zorlar (bayt-aynı).
  * sync: ilk-görüş arm ETMEZ; OFF→ON izlemeye alır; ON→OFF DISARM eder.
  * check: yetersiz örnek → monitoring; post<baseline → ROLLED_BACK (override yazılır);
    post≥baseline → CONFIRMED; süre+kanıtsız → INCONCLUSIVE (guard canlı kalır);
    GUARD_AUTO_DISABLE=0 → ROLLBACK_RECOMMENDED (override YAZILMAZ).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers.technical import timeframe as tf
from packages.data.registry import guard_overrides
from packages.decision import engine
from packages.learning import guard_monitor_store as store
from packages.learning import guard_safety, weight_rollback


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Override + monitor store dosyalarını tmp'e yönlendir (gerçek state'e dokunma)."""
    monkeypatch.setenv("GUARD_OVERRIDES_PATH", str(tmp_path / "guard_overrides.json"))
    monkeypatch.setenv("GUARD_MONITOR_STORE_PATH", str(tmp_path / "guard_monitor.json"))
    # Oto-kapat varsayılan AÇIK olsun (env miras kalmasın).
    monkeypatch.delenv("GUARD_AUTO_DISABLE", raising=False)
    monkeypatch.delenv("GUARD_ROLLBACK_MIN_OUTCOMES", raising=False)
    monkeypatch.delenv("GUARD_MONITOR_MAX_AGE_HOURS", raising=False)
    # mtime-cache'i sıfırla (önceki testten taşmasın).
    guard_overrides._CACHE["key"] = None
    guard_overrides._CACHE["data"] = {"overrides": {}}


# --------------------------------------------------------------------------
# guard_overrides — kill-switch
# --------------------------------------------------------------------------

def test_override_default_is_passthrough():
    assert guard_overrides.is_disabled("chop") is False
    assert guard_overrides.active() == {}


def test_override_set_and_clear_with_cache_invalidation():
    guard_overrides.set_disabled("chop", reason="test")
    assert guard_overrides.is_disabled("chop") is True
    assert "chop" in guard_overrides.active()
    assert guard_overrides.clear("chop") is True
    assert guard_overrides.is_disabled("chop") is False
    # İkinci clear no-op.
    assert guard_overrides.clear("chop") is False


# --------------------------------------------------------------------------
# engine / timeframe seam'leri — override YALNIZ OFF'a zorlar
# --------------------------------------------------------------------------

def test_technical_seam_override_forces_off_only(monkeypatch):
    monkeypatch.setattr(
        tf, "load_thresholds",
        lambda: {"technical": {"trend_quality": {"enabled": True}}},
    )
    # Override yok → config ON birebir yansır.
    assert tf.load_config().chop_guard_enabled is True
    # Override → zorla OFF.
    guard_overrides.set_disabled("chop", reason="test")
    assert tf.load_config().chop_guard_enabled is False
    # Config zaten OFF iken override hiçbir şeyi ON yapmaz.
    monkeypatch.setattr(tf, "load_thresholds", lambda: {"technical": {}})
    assert tf.load_config().chop_guard_enabled is False


def test_self_conflict_seam_override_forces_off(monkeypatch):
    monkeypatch.setattr(
        engine, "load_thresholds",
        lambda: {"book_audit": {"self_conflict_guard": {"enabled": True}}},
    )
    assert engine._self_conflict_cfg().get("enabled") is True
    guard_overrides.set_disabled("self_conflict", reason="test")
    assert engine._self_conflict_cfg().get("enabled") is False


# --------------------------------------------------------------------------
# sync — geçiş tespiti
# --------------------------------------------------------------------------

def _only(states: dict) -> dict:
    base = {k: False for k in guard_safety.guard_keys()}
    base.update(states)
    return base


def test_first_sight_does_not_arm_preexisting_on(monkeypatch):
    # last_seen boş + guard zaten ON → izleme AÇILMAZ, yalnız snapshot.
    monkeypatch.setattr(guard_safety, "_raw_states", lambda: _only({"self_conflict": True}))
    out = guard_safety.sync()
    assert out["armed"] == []
    assert store.get_active("self_conflict") is None
    assert store.get_last_seen()["self_conflict"] is True


def test_off_to_on_arms_with_matched_baseline(monkeypatch):
    store.set_last_seen(_only({"chop": False}))
    monkeypatch.setattr(guard_safety, "_raw_states", lambda: _only({"chop": True}))
    monkeypatch.setattr(weight_rollback, "pre_apply_expectancy", lambda window=None: (12, 0.42))
    out = guard_safety.sync()
    assert out["armed"] == ["chop"]
    active = store.get_active("chop")
    assert active["baseline_expectancy"] == 0.42
    assert active["baseline_n"] == 12


def test_off_to_on_clears_stale_override(monkeypatch):
    # Owner re-promosyonu eski kill'i düşürür (taze deneme).
    guard_overrides.set_disabled("reversion", reason="old")
    store.set_last_seen(_only({"reversion": False}))
    monkeypatch.setattr(guard_safety, "_raw_states", lambda: _only({"reversion": True}))
    monkeypatch.setattr(weight_rollback, "pre_apply_expectancy", lambda window=None: (10, 0.1))
    guard_safety.sync()
    assert guard_overrides.is_disabled("reversion") is False


def test_on_to_off_disarms_owner_disabled(monkeypatch):
    store.record_enable("chop", enabled_at=datetime.now(UTC).isoformat(),
                        baseline_expectancy=0.1, baseline_n=10)
    store.set_last_seen(_only({"chop": True}))
    monkeypatch.setattr(guard_safety, "_raw_states", lambda: _only({"chop": False}))
    monkeypatch.setattr(weight_rollback, "post_open_expectancy", lambda since: (3, 0.2))
    out = guard_safety.sync()
    assert out["disarmed"] == ["chop"]
    assert store.get_active("chop") is None
    assert store.history()[0]["status"] == "DISARMED"


# --------------------------------------------------------------------------
# check_guards — rollback / confirm / monitoring / inconclusive
# --------------------------------------------------------------------------

def _arm(guard_key="chop", *, baseline=0.5, age_hours=1.0):
    enabled_at = (datetime.now(UTC) - timedelta(hours=age_hours)).isoformat()
    store.record_enable(guard_key, enabled_at=enabled_at,
                        baseline_expectancy=baseline, baseline_n=15)


def test_check_monitoring_when_insufficient(monkeypatch):
    _arm()
    monkeypatch.setattr(weight_rollback, "post_open_expectancy", lambda since: (5, 0.1))
    res = guard_safety.check_guards()
    assert res[0]["status"] == "monitoring"
    assert store.get_active("chop") is not None  # izleme sürüyor


def test_check_rolled_back_writes_override(monkeypatch):
    _arm(baseline=0.5)
    monkeypatch.setattr(weight_rollback, "post_open_expectancy", lambda since: (20, 0.1))
    res = guard_safety.check_guards()
    assert res[0]["status"] == "ROLLED_BACK"
    assert res[0]["auto_disabled"] is True
    assert guard_overrides.is_disabled("chop") is True
    assert store.get_active("chop") is None


def test_check_confirmed_keeps_guard_live(monkeypatch):
    _arm(baseline=0.5)
    monkeypatch.setattr(weight_rollback, "post_open_expectancy", lambda since: (20, 0.9))
    res = guard_safety.check_guards()
    assert res[0]["status"] == "CONFIRMED"
    assert guard_overrides.is_disabled("chop") is False
    assert store.get_active("chop") is None


def test_check_expired_no_evidence_is_inconclusive(monkeypatch):
    # 15 gün önce enable + hiç outcome → süre doldu, kanıt yok → guard CANLI kalır.
    _arm(baseline=0.5, age_hours=24 * 15)
    monkeypatch.setattr(weight_rollback, "post_open_expectancy", lambda since: (0, 0.0))
    res = guard_safety.check_guards()
    assert res[0]["status"] == "INCONCLUSIVE"
    assert guard_overrides.is_disabled("chop") is False  # owner niyeti korunur
    assert store.get_active("chop") is None


def test_recommend_only_when_auto_disable_off(monkeypatch):
    monkeypatch.setenv("GUARD_AUTO_DISABLE", "0")
    _arm(baseline=0.5)
    monkeypatch.setattr(weight_rollback, "post_open_expectancy", lambda since: (20, 0.1))
    res = guard_safety.check_guards()
    assert res[0]["status"] == "ROLLBACK_RECOMMENDED"
    assert res[0]["auto_disabled"] is False
    assert guard_overrides.is_disabled("chop") is False  # override YAZILMADI
    assert store.get_active("chop") is None


# --------------------------------------------------------------------------
# adopt — zaten-açık guard'ı izlemeye al (recommend-only)
# --------------------------------------------------------------------------

def test_adopt_arms_only_live_unmonitored_guards(monkeypatch):
    monkeypatch.setattr(guard_safety, "_raw_states", lambda: _only({"chop": True, "reversion": False}))
    monkeypatch.setattr(weight_rollback, "pre_apply_expectancy", lambda window=None: (10, 0.3))
    out = guard_safety.adopt()
    assert out["adopted"] == ["chop"]  # reversion canlı değil → atlanır
    active = store.get_active("chop")
    assert active["mode"] == "adopted"
    assert active["baseline_expectancy"] == 0.3


def test_adopt_skips_already_monitored_and_killed(monkeypatch):
    monkeypatch.setattr(guard_safety, "_raw_states", lambda: _only({"chop": True, "exhaustion": True}))
    monkeypatch.setattr(weight_rollback, "pre_apply_expectancy", lambda window=None: (10, 0.3))
    store.record_enable("chop", enabled_at=datetime.now(UTC).isoformat(),
                        baseline_expectancy=0.1, baseline_n=10)  # zaten izleniyor
    guard_overrides.set_disabled("exhaustion", reason="killed")  # kasa kapatmış
    out = guard_safety.adopt()
    assert out["adopted"] == []


def test_adopted_guard_never_auto_disables(monkeypatch):
    # Oto-kapat AÇIK olsa bile adopted guard sadece ÖNERİ verir (override yazılmaz).
    enabled_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    store.record_enable("chop", enabled_at=enabled_at, baseline_expectancy=0.5,
                        baseline_n=15, mode="adopted")
    monkeypatch.setattr(weight_rollback, "post_open_expectancy", lambda since: (20, 0.1))
    res = guard_safety.check_guards()
    assert res[0]["status"] == "ROLLBACK_RECOMMENDED"
    assert res[0]["auto_disabled"] is False
    assert guard_overrides.is_disabled("chop") is False  # sessizce KAPATMADI


# --------------------------------------------------------------------------
# report — observe view
# --------------------------------------------------------------------------

def test_report_shape_and_effective_state(monkeypatch):
    monkeypatch.setattr(guard_safety, "_raw_states", lambda: _only({"chop": True}))
    guard_overrides.set_disabled("chop", reason="killed")
    rep = guard_safety.report()
    assert rep["available"] is True
    by_key = {g["guard_key"]: g for g in rep["guards"]}
    assert set(by_key) == set(guard_safety.guard_keys())
    chop = by_key["chop"]
    assert chop["config_enabled"] is True
    assert chop["vault_disabled"] is True
    assert chop["effective_enabled"] is False  # config ON ama kasa kapattı
