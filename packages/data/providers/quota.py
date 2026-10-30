"""Ücretsiz sağlayıcı kotaları — günlük ve dakikalık çağrı sayacı (tek yer).

Sağlayıcı ağ çağrısından önce ``consume(name)`` sorar. İzin varsa çağrı sayılır ve
yapılır. Sınır doluysa çağrı yapılmaz: sağlayıcı önbelleğe ya da zincirdeki bir
sonraki kaynağa düşer. Bayat veri "stale" etiketiyle gider; sahte veri üretilmez.
Sayaç ``data/runtime/provider_quota.json``'da kalıcıdır, yani süreç yeniden başlasa
da gün içi sayım sürer; UTC gün dönümünde sıfırlanır.

Sınırlar sağlayıcıların ücretsiz planlarının biraz altında tutulur (2026-10-30
ölçümü): CoinGecko aylık 10.000 çağrı (~320/gün), AlphaVantage 25/gün, TwelveData
800/gün ve 8/dk, Finnhub 60/dk, Tavily aylık 1000 kredi. Ortam değişkeniyle
değiştirilebilir: ``PROVIDER_QUOTA_<AD>_PER_DAY`` / ``_PER_MINUTE`` (0 = sınırsız).
"""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from packages.ops.store import write_text_atomic

DEFAULT_LIMITS: dict[str, dict[str, int]] = {
    "coingecko": {"per_day": 300, "per_minute": 25},
    "alphavantage": {"per_day": 20, "per_minute": 4},
    "twelvedata": {"per_day": 700, "per_minute": 7},
    "finnhub": {"per_day": 0, "per_minute": 50},
    "tavily": {"per_day": 30, "per_minute": 0},
}

_LOCK = threading.Lock()
_STATE: dict | None = None
_STATE_PATH: str | None = None


def _path() -> Path:
    return Path(os.environ.get("PROVIDER_QUOTA_PATH", "data/runtime/provider_quota.json"))


def limits(name: str) -> dict[str, int]:
    base = dict(DEFAULT_LIMITS.get(name, {"per_day": 0, "per_minute": 0}))
    for key in ("per_day", "per_minute"):
        raw = os.environ.get(f"PROVIDER_QUOTA_{name.upper()}_{key.upper()}")
        if raw is not None:
            try:
                base[key] = max(0, int(raw))
            except ValueError:
                pass
    return base


def _load() -> dict:
    global _STATE, _STATE_PATH
    path = _path()
    if _STATE is not None and _STATE_PATH == str(path):
        return _STATE
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    _STATE, _STATE_PATH = state, str(path)
    return state


def _save(state: dict) -> None:
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, json.dumps(state, ensure_ascii=False, sort_keys=True))
    except (OSError, TypeError, ValueError):
        return  # sayaç yazılamazsa veri akışı durmaz


def consume(name: str, *, now: Callable[[], datetime] | None = None) -> bool:
    """Bir çağrı hakkı iste; varsa say ve True dön, yoksa False (çağrı yapılmaz)."""
    current = (now or (lambda: datetime.now(UTC)))()
    day = current.strftime("%Y-%m-%d")
    minute = current.strftime("%Y-%m-%dT%H:%M")
    lim = limits(name)
    with _LOCK:
        state = _load()
        row = state.get(name) or {}
        if row.get("day") != day:
            row = {"day": day, "count": 0, "minute": minute, "minute_count": 0, "denied": 0}
        if row.get("minute") != minute:
            row["minute"], row["minute_count"] = minute, 0
        over_day = lim["per_day"] > 0 and int(row.get("count", 0)) >= lim["per_day"]
        over_minute = lim["per_minute"] > 0 and int(row.get("minute_count", 0)) >= lim["per_minute"]
        if over_day or over_minute:
            row["denied"] = int(row.get("denied", 0)) + 1
            row["last_denied"] = "day" if over_day else "minute"
            state[name] = row
            _save(state)
            return False
        row["count"] = int(row.get("count", 0)) + 1
        row["minute_count"] = int(row.get("minute_count", 0)) + 1
        state[name] = row
        _save(state)
        return True


def usage() -> dict[str, dict]:
    """Bugünkü kullanım ve sınırlar (sağlık ve panel görünümü için)."""
    with _LOCK:
        state = _load()
        return {
            name: {**limits(name), **{k: v for k, v in (state.get(name) or {}).items()}}
            for name in sorted(set(DEFAULT_LIMITS) | set(state))
        }


def reset_cache() -> None:
    """Testler arası sızıntıyı önlemek için."""
    global _STATE, _STATE_PATH
    with _LOCK:
        _STATE, _STATE_PATH = None, None


__all__ = ["DEFAULT_LIMITS", "consume", "limits", "reset_cache", "usage"]
