"""Makro sürpriz → varlık yönü için tek tablo.

`config/macro_surprise_matrix_v1.0.yaml` okunur; nedensellik (bayrakla), makro
kanıt ve olay-sonrası takip yönü buradan alır. Ağırlık pozitif normalleştirilmiş
sürpriz içindir (bkz. dosya başlığı). Ağ çağrısı yok, karar vermez.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_PATH = Path(__file__).resolve().parents[2] / "config" / "macro_surprise_matrix_v1.0.yaml"
_CACHE: dict[str, Any] | None = None


def enabled() -> bool:
    """Nedensellik katmanında tablo kullanımı (varsayılan kapalı; owner onayıyla açılır)."""
    return os.environ.get("EYAY_MACRO_MATRIX_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _data() -> dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            _CACHE = {}
    return _CACHE


def topic_for(name: str | None) -> str | None:
    """Konu adı ya da takma adını tablodaki konuya çevirir; bilinmiyorsa None."""
    if not name:
        return None
    data = _data()
    key = (data.get("aliases") or {}).get(str(name), str(name))
    return key if key in (data.get("topics") or {}) else None


def raw_sign(topic: str) -> int:
    """Ham sürprizin (gerçekleşen − beklenti) normalleştirilmiş yöne çevrilmesi."""
    return -1 if topic in (_data().get("flip_raw_surprise") or ()) else 1


def weight(topic: str | None, symbol: str, asset_class: str | None = None) -> float:
    """Pozitif sürprizde varlığın ilk tepki ağırlığı; tabloda yoksa 0 (belirsiz)."""
    row = (_data().get("topics") or {}).get(topic or "") or {}
    symbols = row.get("symbols") or {}
    if symbol in symbols:
        return float(symbols[symbol])
    return float((row.get("classes") or {}).get(asset_class or "", 0.0))


def thesis_weight() -> float:
    try:
        return max(0.0, min(1.0, float(_data().get("thesis_weight", 0.35))))
    except (TypeError, ValueError):
        return 0.35


def symbols(topic: str | None) -> tuple[str, ...]:
    """Konunun yön verdiği semboller (ağırlığı 0 olmayanlar)."""
    row = (_data().get("topics") or {}).get(topic or "") or {}
    return tuple(sym for sym, w in (row.get("symbols") or {}).items() if float(w) != 0)


def expected_signs(topic: str | None, positive: bool) -> dict[str, int]:
    """Olay-sonrası takip için sembol başına beklenen yön (+1/−1); belirsizler atlanır."""
    row = (_data().get("topics") or {}).get(topic or "") or {}
    sign = 1 if positive else -1
    return {sym: (1 if float(w) > 0 else -1) * sign for sym, w in (row.get("symbols") or {}).items() if float(w) != 0}


def reset_cache() -> None:
    global _CACHE
    _CACHE = None
