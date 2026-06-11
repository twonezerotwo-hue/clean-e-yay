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

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Tüm testler için mock fixture flag (data policy gereği runtime mock yasak).
os.environ.setdefault("TEST_USE_MOCK", "true")
