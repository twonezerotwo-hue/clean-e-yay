"""Golden replay kapısı — canlı config ile karar matrisi bayt-aynı kalmalı.

Ayrı bir süreçte koşar: conftest'in test-baseline pinleri (canlı flag'leri KAPATAN
autouse fixture'lar) bu kontrole sızmasın. Fark çıkarsa:
  - Değişiklik davranışı DEĞİŞTİRMEMELİYDİ → hata; düzelt.
  - Değişiklik bilinçli bir mantık düzeltmesiyse → PR açıklamasına farkı yaz ve
    `python -m tests.golden.golden_replay --write` ile golden'ı güncelle.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_golden_replay_byte_identical() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "tests.golden.golden_replay", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
