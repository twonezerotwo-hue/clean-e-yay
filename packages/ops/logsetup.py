"""Çıktı/log kurulumu — Windows'ta Türkçe karakter bozulmasını önler.

Keeper, supervisor/tick/learning çıktısını dosyaya yönlendirir (`logs/*.log`).
Windows'ta varsayılan akış kodlaması UTF-8 olmadığı için log satırlarındaki
Türkçe karakterler bozuk görünüyordu (owner notu 2026-10-06; veri kaybı yok).
Tüm çalıştırma yolları tek yerden ASCII-dışı karakterleri güvenle yazsın diye
akışlar UTF-8'e çevrilir ve standart log şeması burada kurulur.
"""
from __future__ import annotations

import logging
import sys


def enable_utf8_output() -> None:
    """sys.stdout/stderr'i UTF-8'e çevir; desteklemeyen akışta sessizce geç."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def configure_logging() -> None:
    """UTF-8 akışlar + standart INFO şeması (tüm entrypoint'ler için tek yol)."""
    enable_utf8_output()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


__all__ = ["configure_logging", "enable_utf8_output"]
