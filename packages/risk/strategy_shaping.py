"""Strateji-farkında işlem şekillendirme (Faz 4) — saf fonksiyon.

Setup Classifier'ın ürettiği `setup_type` (TREND_LONG, REVERSAL_SHORT_CONFIRMED,
RANGE_LONG, BREAKOUT_SHORT, PULLBACK_LONG, SCALP_LONG, …) tek bir strateji ailesine
indirger ve o aileye göre TABAN geometriye uygulanacak çarpanları döner:

  stop_mult   — SL mesafesi çarpanı (REVERSAL yakın stop 0.85, SCALP çok dar 0.75)
  tp_rr_mult  — R:R çarpanı (TREND yüksek 1.15, RANGE düşük 0.8)
  trail_mult  — trailing gevşemesi (TREND 1.25 kazananı sür, SCALP 0.75 sıkı)
  size_mult   — boyut çarpanı (yalnız KÜÇÜLTÜR, ≤ 1.0 — no-boost invariant)

DEĞİŞMEZ GÜVENLİK
-----------------
- Flag OFF (config strategy_shaping.enabled=false) → NÖTR (hepsi 1.0) → bayt-aynı.
- `setup_type` None/bilinmiyor/NO_TRADE → NÖTR (tanımadığını şekillendirme).
- Tüm çarpanlar guardrail [0.5, 1.5]'e clamp'lenir (bozuk config extreme yapamaz).
- size_mult ayrıca ≤ 1.0'a clamp'lenir (boyutu ASLA artırma; mevcut no-AI-boost yasası).

Karar zincirine bağlı DEĞİL — yalnız çarpan üretir; çağıran (lifecycle.open_position
flag açıkken, shadow gözlemde her zaman) uygular. PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.registry.loader import load_thresholds

_MIN_MULT = 0.5
_MAX_MULT = 1.5

# setup_type → strateji ailesi. En SPESİFİK önce (REVERSAL_*_CONFIRMED, _WATCH).
_FAMILIES = (
    ("REVERSAL", "CONFIRMED", "REVERSAL_CONFIRMED"),
    ("REVERSAL", "WATCH", "REVERSAL_WATCH"),
    ("BREAKOUT", "", "BREAKOUT"),
    ("PULLBACK", "", "PULLBACK"),
    ("SCALP", "", "SCALP"),
    ("RANGE", "", "RANGE"),
    ("TREND", "", "TREND"),
)


@dataclass(frozen=True)
class Shaping:
    """Taban geometriye uygulanacak strateji çarpanları. NÖTR = hepsi 1.0."""
    family: str | None      # eşleşen strateji ailesi (None = nötr)
    stop_mult: float = 1.0
    tp_rr_mult: float = 1.0
    trail_mult: float = 1.0
    size_mult: float = 1.0

    @property
    def active(self) -> bool:
        return self.family is not None


NEUTRAL = Shaping(family=None)


def _cfg() -> dict:
    """strategy_shaping config (monkeypatch-seam). enabled default False (bayt-aynı)."""
    return load_thresholds().get("strategy_shaping") or {}


def _family_of(setup_type: str | None) -> str | None:
    """setup_type → strateji ailesi anahtarı (config'teki profiles anahtarı)."""
    if not setup_type or setup_type == "NO_TRADE":
        return None
    for base, needle, key in _FAMILIES:
        if setup_type.startswith(base) and (not needle or needle in setup_type):
            return key
    return None


def _clamp(v: float, *, cap: float = _MAX_MULT) -> float:
    return max(_MIN_MULT, min(cap, float(v)))


def shape(setup_type: str | None) -> Shaping:
    """`setup_type` için şekillendirme çarpanları. Flag OFF / tanınmayan → NÖTR."""
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return NEUTRAL
    family = _family_of(setup_type)
    if family is None:
        return NEUTRAL
    prof = (cfg.get("profiles") or {}).get(family)
    if not isinstance(prof, dict):
        return NEUTRAL
    return Shaping(
        family=family,
        stop_mult=_clamp(prof.get("stop", 1.0)),
        tp_rr_mult=_clamp(prof.get("tp_rr", 1.0)),
        trail_mult=_clamp(prof.get("trail", 1.0)),
        size_mult=_clamp(prof.get("size", 1.0), cap=1.0),  # yalnız küçültür (no-boost)
    )


__all__ = ["NEUTRAL", "Shaping", "shape"]
