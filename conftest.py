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
def _isolate_decision_log(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Signal-attribution log is local-only: the close path writes a decision_log
    entry on every trade close. Redirect it to a session tmp file so the suite never
    appends to the real data/runtime/decision_log.jsonl. Per-test fixtures may still
    override DECISION_LOG_PATH via monkeypatch to assert on contents.
    """
    os.environ["DECISION_LOG_PATH"] = str(
        tmp_path_factory.mktemp("decision_log") / "decision_log.jsonl"
    )
