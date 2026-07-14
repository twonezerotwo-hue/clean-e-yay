"""F5-3 — aktivasyon watchdog'u (owner-flag outcome izleyicisi) testleri.

- İlk görüşte zaten-ON flag izlemeye ALINMAZ (yalnız snapshot).
- OFF→ON → baseline damgalanıp izleme açılır; ON→OFF → DISARMED.
- Yeterli outcome: post ≥ baseline → CONFIRMED; post < baseline → DEGRADED.
- YALNIZ-ÖNERİ değişmezi: DEGRADED hiçbir override/config YAZMAZ.
- report() flag durumlarını + izleme ilerlemesini döner; bozuk store → boş default.
"""
from __future__ import annotations

import json

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import activation_watchdog as aw

_FLAG_ON = {"news": {"sentiment_v2": True}}


@pytest.fixture
def wd_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTIVATION_WATCHDOG_PATH", str(tmp_path / "watchdog.json"))
    monkeypatch.setenv("ACTIVATION_MIN_OUTCOMES", "3")
    # ölçüm fonksiyonlarını deterministik sabitle (kaynak: weight_rollback)
    monkeypatch.setattr(aw.weight_rollback, "pre_apply_expectancy", lambda window: (3, 10.0))
    monkeypatch.setattr(aw.weight_rollback, "post_open_expectancy", lambda ts: (0, 0.0))
    return tmp_path


def test_numeric_flag_enabled_reading() -> None:
    """Sayısal flag (min_module_coverage/hysteresis_band): 0=KAPALI, >0=AÇIK."""
    with threshold_override({"consensus": {"min_module_coverage": 0.0}}):
        assert aw._flag_enabled("consensus_min_module_coverage") is False
    with threshold_override({"consensus": {"min_module_coverage": 0.6}}):
        assert aw._flag_enabled("consensus_min_module_coverage") is True
    with threshold_override({"regime": {"hysteresis_band": 3.0}}):
        assert aw._flag_enabled("regime_hysteresis_band") is True


def test_denetim_flags_registered() -> None:
    """M7-M18 gölge flag'leri REGISTRY'de (aktivasyon izleme altyapısı hazır)."""
    for key in (
        "consensus_dominant_directional", "consensus_quantum_regime_gate",
        "regime_hysteresis_band", "consensus_fundamental_v4", "regime_liquidity_momentum",
    ):
        assert key in aw.REGISTRY


def test_first_sight_already_on_not_monitored(wd_env) -> None:
    with threshold_override(_FLAG_ON):
        out = aw.sync()
    assert out == {"armed": [], "disarmed": []}  # snapshot-only (owner-niyeti)
    assert aw.report()["flags"][0]["monitoring"] is False


def test_off_to_on_arms_and_on_to_off_disarms(wd_env) -> None:
    aw.sync()  # ilk görüş: hepsi OFF snapshot'landı
    with threshold_override(_FLAG_ON):
        out = aw.sync()
    assert out["armed"] == ["news_sentiment_v2"]
    rep = aw.report()
    flag = next(f for f in rep["flags"] if f["flag_key"] == "news_sentiment_v2")
    assert flag["monitoring"] is True
    assert flag["monitor"]["baseline_expectancy"] == 10.0
    # owner kapattı → DISARMED (watchdog kapatmadı)
    out2 = aw.sync()
    assert out2["disarmed"] == ["news_sentiment_v2"]
    assert aw.report()["history"][0]["outcome"] == "DISARMED"


def test_env_flag_transition(wd_env, monkeypatch) -> None:
    aw.sync()
    monkeypatch.setenv("MISTAKE_MEMORY_V2", "1")
    out = aw.sync()
    assert out["armed"] == ["mistake_memory_v2"]


def test_tf_target_auto_only_arms_on_activation(wd_env, monkeypatch) -> None:
    """E-4 aktivasyonu izlenir: ilk sync OFF snapshot'lar, AUTO_ONLY=1 → arm.
    Aktivasyon sıralamasının (önce kaydet, sonra aç) kanıtı."""
    aw.sync()  # ilk görüş: AUTO_ONLY OFF olarak last_seen'e yazılır
    monkeypatch.setenv("TF_TARGET_AUTO_ONLY", "1")
    out = aw.sync()
    assert out["armed"] == ["tf_target_auto_only"]
    flag = next(f for f in aw.report()["flags"] if f["flag_key"] == "tf_target_auto_only")
    assert flag["monitoring"] is True
    assert flag["monitor"]["baseline_expectancy"] == 10.0


def test_confirmed_and_degraded_decisions(wd_env, monkeypatch) -> None:
    aw.sync()
    with threshold_override(_FLAG_ON):
        aw.sync()
        # yeterli outcome + post ≥ baseline → CONFIRMED
        monkeypatch.setattr(aw.weight_rollback, "post_open_expectancy", lambda ts: (5, 12.0))
        checks = aw.check()
    assert checks[0]["status"] == "CONFIRMED"
    assert aw.report()["history"][0]["outcome"] == "CONFIRMED"

    # ikinci tur: yeniden aç (OFF görülmüş olmalı) → DEGRADED yolu
    aw.sync()  # flag artık OFF → last_seen güncellenir (izleme yok, resolve edilmişti)
    with threshold_override(_FLAG_ON):
        aw.sync()
        monkeypatch.setattr(aw.weight_rollback, "post_open_expectancy", lambda ts: (5, 4.0))
        checks = aw.check()
    assert checks[0]["status"] == "DEGRADED"


def test_recommend_only_never_writes_overrides(wd_env, monkeypatch, tmp_path) -> None:
    """DEĞİŞMEZ: DEGRADED bile hiçbir override dosyası yazmaz (yalnız-öneri)."""
    ov_path = tmp_path / "guard_overrides.json"
    monkeypatch.setenv("GUARD_OVERRIDES_PATH", str(ov_path))
    aw.sync()
    with threshold_override(_FLAG_ON):
        aw.sync()
        monkeypatch.setattr(aw.weight_rollback, "post_open_expectancy", lambda ts: (5, -99.0))
        checks = aw.check()
    assert checks[0]["status"] == "DEGRADED"
    assert not ov_path.exists()  # kill-override YOK
    # flag hâlâ owner'ın bıraktığı gibi okunur (watchdog dokunmadı)
    with threshold_override(_FLAG_ON):
        assert aw._flag_enabled("news_sentiment_v2") is True


def test_monitoring_until_enough_outcomes(wd_env) -> None:
    aw.sync()
    with threshold_override(_FLAG_ON):
        aw.sync()
        checks = aw.check()  # post_n=0 < 3 → beklemede
    assert checks[0]["status"] == "monitoring"
    # izleme hâlâ açık (resolve edilmedi)
    assert aw.report()["flags"][0]["monitoring"] is True


def test_corrupt_store_safe_default(wd_env, tmp_path) -> None:
    (tmp_path / "watchdog.json").write_text("{bozuk", encoding="utf-8")
    rep = aw.report()
    assert rep["available"] is True and rep["history"] == []


def test_registry_covers_pending_activations() -> None:
    """Roadmap'teki bekleyen aktivasyonlar kayıtlı (yeni flag → buraya satır)."""
    keys = set(aw.REGISTRY)
    assert {
        "news_sentiment_v2", "regime_drop_unavailable_layers",
        "consensus_fundamental_v2", "sentinel_v2", "correlation_price_returns",
        "tf_platt", "empirical_pwin",
        "weight_regime_filter", "mistake_memory_v2", "expectancy_r_mode",
        # E serisi — çıkış/stop öğrenme flag'leri (denetim 2026-07-03)
        "tf_target_auto_only", "tf_target_edge_gate", "exit_forensics_nudge",
    } <= keys
    payload = json.dumps(aw.report(), default=str)
    assert "recommend_only" in payload
