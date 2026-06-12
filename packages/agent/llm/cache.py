"""2 saatlik file-backed LLM yanıt cache'i.

Anahtar içerik bazlıdır (compact context digest) — snapshot_id her 30sn
değiştiği için anahtara girmez; state aynı kaldıkça cache vurur.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

DEFAULT_PATH = "data/runtime/llm_cache.json"
DEFAULT_TTL_SEC = 2 * 60 * 60  # 2 saat


def _path() -> Path:
    return Path(os.environ.get("LLM_CACHE_PATH", DEFAULT_PATH))


def ttl_sec() -> float:
    try:
        return float(os.environ.get("LLM_CACHE_TTL_SEC", DEFAULT_TTL_SEC))
    except ValueError:
        return float(DEFAULT_TTL_SEC)


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def get(key: str) -> dict | None:
    entry = _load().get(key)
    if not isinstance(entry, dict):
        return None
    if time.time() - float(entry.get("at") or 0) > ttl_sec():
        return None
    value = entry.get("value")
    return value if isinstance(value, dict) else None


def put(key: str, value: dict) -> None:
    data = _load()
    now = time.time()
    # Süresi geçen girişleri budayarak yaz (dosya sınırsız büyümesin).
    data = {
        k: v
        for k, v in data.items()
        if isinstance(v, dict) and now - float(v.get("at") or 0) <= ttl_sec()
    }
    data[key] = {"at": now, "value": value}
    _save(data)
