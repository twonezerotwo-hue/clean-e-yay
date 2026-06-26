"""Trade Profile Selector — spec §23. EVIDENCE only, saf fonksiyon.

Setup Classifier'ın ürettiği setup_type + entry_timeframe'i tek bir trade
profile'a (SCALP/INTRADAY/TACTICAL/SWING/POSITION) indirger. Hiçbir karar
zincirine bağlı DEĞİLDİR.
"""
from __future__ import annotations

from packages.mode.config import TRADE_PROFILES

_TF_PROFILE = {
    "15m": "INTRADAY",
    "1h": "INTRADAY",
    "4h": "TACTICAL",
    "1d": "SWING",
    "1w": "POSITION",
}


def select_profile(setup_type: str, entry_timeframe: str | None) -> str | None:
    """`setup_type` NO_TRADE ise profile yok (None). SCALP_* setup'lar her
    zaman SCALP profiline gider (timeframe ne olursa olsun — setup classifier
    zaten SCALP_* üretmek için kısa timeframe şartını uygulamıştı)."""
    if setup_type == "NO_TRADE":
        return None
    if setup_type.startswith("SCALP_"):
        return "SCALP"
    return _TF_PROFILE.get(entry_timeframe or "", None)


__all__ = ["select_profile", "TRADE_PROFILES"]
