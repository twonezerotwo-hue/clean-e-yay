"""Grafik desen sağlayıcısı — v2.2 sırasında implement edilecek.

Şimdilik consensus motorunun beklediği sözleşmeye uygun boş liste döner;
böylece "chart_pattern" modülü mevcut değilse ağırlık otomatik yeniden
dağıtılır (consensus engine bunu zaten yapar).
"""
from __future__ import annotations


def list_detections(symbol: str) -> list[dict]:
    return []


def has_data() -> bool:
    return False
