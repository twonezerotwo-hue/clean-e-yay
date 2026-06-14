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
