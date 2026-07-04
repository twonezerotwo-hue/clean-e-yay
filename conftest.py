"""pytest kök configürasyonu.

- Repo root'unu sys.path'e ekler.
- Tüm test session'ı boyunca `TEST_USE_MOCK=true` set eder:
  data policy gereği runtime'da mock fallback yasaktır; testler bu
  fixture flag'i ile mock kullanır. Testler isterlerse `monkeypatch`
  ile bu flag'i kapatıp live-fail davranışını doğrulayabilir.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Tüm testler için mock fixture flag (data policy gereği runtime mock yasak).
os.environ.setdefault("TEST_USE_MOCK", "true")


@pytest.fixture(autouse=True)
def _f5_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """F5 (EV kapısı + Kelly sizing) canlı config'te AÇIK, ama çoğu unit test pre-F5
    sizing/açılış davranışını varsayar (relatif size karşılaştırmaları, açık sayısı).
    Testlerde default KAPAT — F5'i doğrulayan testler explicit monkeypatch ile açar.
    Böylece F5 canlı enable'ı mevcut testleri bozmaz; F5 davranışı ayrı doğrulanır
    (test_ev_kelly helper'ları + expected_value wiring + enabled-gate testi)."""
    from packages.decision import engine
    monkeypatch.setattr(engine, "_ev_gate_cfg", lambda: {"enabled": False})
    monkeypatch.setattr(engine, "_kelly_cfg", lambda: {"enabled": False})


@pytest.fixture(autouse=True)
def _package1_flags_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Paket-1 aktivasyonu (2026-07-02, owner kararı) canlı config'te 5 girdi-düzeltme
    flag'ini AÇTI; unit testlerin çoğu v1 baseline davranışını varsayar (matrix
    fixture'ları, bayt-aynılık assertion'ları). Testlerde default KAPAT — v2
    davranışını doğrulayan testler `threshold_override` ile açar (ctx override
    base'in ÜSTÜNE merge edilir, bu pin onları etkilemez). `_f5_disabled_by_default`
    deseninin devamı: canlı aktivasyonlar test suite'ini KIRMAZ, her davranış
    testi hangi modda koştuğunu kendi seçer."""
    import copy

    from packages.data.registry import loader
    pinned = copy.deepcopy(loader._load_thresholds_base())
    pinned.setdefault("consensus", {})["fundamental_v2"] = False
    pinned.setdefault("news", {})["sentiment_v2"] = False
    pinned.setdefault("regime", {})["drop_unavailable_layers"] = False
    pinned.setdefault("sentinel_v2", {})["enabled"] = False
    pinned.setdefault("risk_gates", {})["correlation_price_returns"] = False
    # Paket 2 / (1) — tf_platt AÇILDI (2026-07-02); testler global-fit baseline'ı
    # pinler, F4-1 davranış testleri threshold_override ile açar.
    pinned.setdefault("calibration", {})["tf_platt"] = False
    # S3-1/S3-2 (2026-07-04) — empirical_pwin + htf_alignment AÇILDI; suite v1
    # baseline'ı pinler, davranış testleri threshold_override/monkeypatch ile açar.
    pinned.setdefault("empirical_pwin", {})["enabled"] = False
    pinned.setdefault("technical", {}).setdefault("htf_alignment", {})["enabled"] = False
    # S2-1 — MTM gate flag'i kayıt fazında zaten false; ileride aktive edilince
    # suite baseline'da kalsın diye şimdiden pinlenir (testler explicit açar).
    pinned.setdefault("risk_gates", {})["mtm_equity_enabled"] = False
    monkeypatch.setattr(loader, "_load_thresholds_base", lambda: pinned)
    # Denetim 2026-07-03 — çıkış-makinesi env flag'leri testlerde default OFF
    # (dev makinesinde .env yüklenmiş olabilir; testler baseline'ı varsayar).
    monkeypatch.delenv("TF_TARGET_AUTO_ONLY", raising=False)
    monkeypatch.delenv("EXIT_FORENSICS_NUDGE", raising=False)
    monkeypatch.delenv("TF_TARGET_EDGE_GATE", raising=False)
    # Aynı sızıntı sınıfı, canlıda görüldü: apps.api.main import'u .env'i
    # os.environ'a yükler; sabah aktivasyonu TF_CALIBRATION_AUTO_ONLY=1 tam
    # koşuda tf_calibration testlerine sızıyordu (fingerprint'siz fikstürler
    # boş dönüyor). Flag'i test eden testler kendi monkeypatch.setenv'iyle açar.
    monkeypatch.delenv("TF_CALIBRATION_AUTO_ONLY", raising=False)
    # Chat model sırası (2026-07-03) — testler default Groq-önce sırayı varsayar;
    # dev .env'inde lokal-önce açık olabilir, sızdırma.
    monkeypatch.delenv("CHAT_LLM_LOCAL_FIRST", raising=False)


@pytest.fixture(autouse=True, scope="session")
def _isolate_runtime_stores(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Redirect file-backed runtime stores under data/runtime/ to session tmp files so
    the suite never reads or writes the real on-disk state. Without this, leftover
    runtime state leaks into unit tests — e.g. an active DAILY_LOSS halt persisted in
    data/runtime/risk_halts.json makes RiskGate return KILL_SWITCH for otherwise-clean
    inputs, masking the event-risk gate. Per-test fixtures may still override these
    paths via monkeypatch to exercise specific contents.
    """
    runtime = tmp_path_factory.mktemp("runtime")
    os.environ["DECISION_LOG_PATH"] = str(runtime / "decision_log.jsonl")
    os.environ["RISK_HALT_PATH"] = str(runtime / "risk_halts.json")
    # F4-2 — karar motoru her decide çağrısında bu artifact'ı okur; suite gerçek
    # diskteki tabloyu görmesin (bayt-aynılık assertion'ları deterministik kalsın).
    os.environ["EMPIRICAL_PWIN_PATH"] = str(runtime / "empirical_pwin.json")
    # Aynı sebep: canlı learning worker'ın fit ettiği data/runtime/platt.json karar
    # motorunun predict_calibrated'ına sızıyordu (testte identity bekleyen assertion
    # makinede fit varken şaşar). Per-test fixture'lar yine override edebilir.
    os.environ["CALIBRATION_STORE_PATH"] = str(runtime / "platt.json")
    # F5-3 — learning worker testleri activation watchdog store'unu gerçek
    # data/runtime'a yazmasın.
    os.environ["ACTIVATION_WATCHDOG_PATH"] = str(runtime / "activation_watchdog.json")
    # Çıkış Otopsisi (2026-07-03) — worker testleri gerçek snapshot'ı ezmesin.
    os.environ["EXIT_FORENSICS_OUT_PATH"] = str(runtime / "exit_forensics.json")
