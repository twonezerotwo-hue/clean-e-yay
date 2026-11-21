"""Konviksiyon-kademeli risk — kalibre güven p(win) → risk kademesi.

config/risk_tiers.yaml tek kaynak. Kademe; boyut/stop/vade/trailing çarpanlarını
belirler. Zayıf konviksiyon = küçük boyut + yakın stop + kısa vade + sıkı trailing.
PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache

import yaml

from packages.data.registry.loader import CONFIG_DIR


@dataclass(frozen=True)
class Tier:
    name: str
    min_conf: float
    size_mult: float
    sl_mult: float
    time_mult: float
    trail_distance: float


# Güven bilinmiyorsa (legacy/None) nötr kademe — hiçbir şeyi değiştirmez.
_NEUTRAL = Tier("NEUTRAL", 0.0, 1.0, 1.0, 1.0, 0.02)


# Yüklenen risk kademeleri dosyasının özeti (açılış damgası için, D7).
_LOADED: dict = {"sha": None}


@lru_cache(maxsize=1)
def _config() -> dict:
    raw = (CONFIG_DIR / "risk_tiers.yaml").read_bytes()
    _LOADED["sha"] = hashlib.sha256(raw).hexdigest()[:12]
    return yaml.safe_load(raw.decode("utf-8")) or {}


def tiers_sha() -> str | None:
    """Bu süreçte YÜKLENMİŞ risk_tiers.yaml özeti (12 hex)."""
    _config()
    return _LOADED["sha"]


@lru_cache(maxsize=1)
def _tiers() -> tuple[Tier, ...]:
    raw = _config().get("tiers") or []
    tiers = [
        Tier(
            name=str(t["name"]),
            min_conf=float(t["min_conf"]),
            size_mult=float(t.get("size_mult", 1.0)),
            sl_mult=float(t.get("sl_mult", 1.0)),
            time_mult=float(t.get("time_mult", 1.0)),
            trail_distance=float(t.get("trail_distance", 0.02)),
        )
        for t in raw
    ]
    return tuple(sorted(tiers, key=lambda x: x.min_conf))


def trail_activate() -> float:
    return float(_config().get("trail_activate", 0.01))


def tier_for(p_win: float | None) -> Tier:
    """p(win)'e karşılık gelen kademe — min_conf'u aşan EN YÜKSEK kademe.
    None ise nötr (çarpan yok). Hiçbiri uymazsa en düşük kademe (floor zaten
    consensus.min_open_confidence ile uygulanır)."""
    if p_win is None:
        return _NEUTRAL
    tiers = _tiers()
    if not tiers:
        return _NEUTRAL
    match = _NEUTRAL
    for t in tiers:  # min_conf artan
        if p_win >= t.min_conf:
            match = t
    # p_win en düşük kademenin de altındaysa en düşüğü uygula (defensive)
    return match if match is not _NEUTRAL else tiers[0]
