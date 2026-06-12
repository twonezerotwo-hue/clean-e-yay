"""Günlük token bütçesi + per-request limit (file-backed, UTC gün bazlı).

Bütçe aşılırsa LLM çağrısı yapılmaz → deterministik fallback. Dosya
bozuksa/yoksa sıfırdan başlar; exception kaçırılmaz.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_PATH = "data/runtime/llm_budget.json"
DEFAULT_DAILY_TOKEN_BUDGET = 100_000
DEFAULT_MAX_TOKENS_PER_REQUEST = 600


def _path() -> Path:
    return Path(os.environ.get("LLM_BUDGET_PATH", DEFAULT_PATH))


def daily_budget() -> int:
    try:
        return int(os.environ.get("LLM_DAILY_TOKEN_BUDGET", DEFAULT_DAILY_TOKEN_BUDGET))
    except ValueError:
        return DEFAULT_DAILY_TOKEN_BUDGET


def max_tokens_per_request() -> int:
    try:
        return int(
            os.environ.get("LLM_MAX_TOKENS_PER_REQUEST", DEFAULT_MAX_TOKENS_PER_REQUEST)
        )
    except ValueError:
        return DEFAULT_MAX_TOKENS_PER_REQUEST


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _load() -> dict:
    p = _path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
    except (OSError, json.JSONDecodeError):
        return {}
    if data.get("date") != _today():
        return {}  # yeni gün → sayaç sıfır
    return data


def _save(data: dict) -> None:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # bütçe persist edilemezse bile akış crash etmez


def used_tokens() -> int:
    return int(_load().get("used_tokens") or 0)


def can_spend(estimated_tokens: int) -> bool:
    return used_tokens() + max(0, int(estimated_tokens)) <= daily_budget()


def record(used: int) -> None:
    data = _load()
    data["date"] = _today()
    data["used_tokens"] = int(data.get("used_tokens") or 0) + max(0, int(used))
    _save(data)


def status() -> dict:
    used = used_tokens()
    budget = daily_budget()
    return {
        "date": _today(),
        "used_tokens": used,
        "daily_budget": budget,
        "remaining": max(0, budget - used),
        "max_tokens_per_request": max_tokens_per_request(),
    }
