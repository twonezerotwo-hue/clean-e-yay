"""Keşif motoru (K serisi) — "analiz sabit, varlık değişken".

Geniş evrende (sektör ETF'leri, ileride kripto top-50) mevcut analiz zinciri
GÖLGEDE koşulur; işlem AÇILMAZ, canlı karar zinciri / RiskGate / tik süresi
DOKUNULMAZ. Tek giriş kapısı `DISCOVERY_SCAN_ENABLED` env flag'idir
(DEFAULT OFF): kapalıyken hiçbir modül ağa çıkmaz, hiçbir dosya yazmaz —
learning koşusu bayt-eşdeğer kalır. Plan: docs/AUDIT_ROADMAP.md K serisi.
"""
from __future__ import annotations

import os

_OFF_VALUES = {"0", "false", "no", "off", ""}


def scan_enabled() -> bool:
    """DISCOVERY_SCAN_ENABLED açık mı? (TF_TARGET_EDGE_GATE deseni — default OFF.)"""
    return os.environ.get("DISCOVERY_SCAN_ENABLED", "0").strip().lower() not in _OFF_VALUES
