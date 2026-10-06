"""Günlük token bütçesi + per-request limit (file-backed, UTC gün bazlı).

Bütçe aşılırsa LLM çağrısı yapılmaz → deterministik fallback. Dosya
bozuksa/yoksa sıfırdan başlar; exception kaçırılmaz.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


# Ortak bütçe yalnız ÜCRETLİ sağlayıcıları sınırlar. Karar MODA göre değil, isteği
# GERÇEKTEN kimin karşıladığına göre verilir: Ollama modunda bile sohbet önce Groq/
# OpenRouter'a gider (get_chat_client), o kullanım sayılmalı ve kilitlenmelidir.
# `mock` test çifti ücretli sağlayıcıyı taklit eder → sayılır (listede yok).
LOCAL_SOURCES: frozenset[str] = frozenset({"ollama"})


def is_local(source: str | None) -> bool:
    """Bu sağlayıcı (LLMCompletion.source / client.name) yerel ve ücretsiz mi?"""
    return (source or "").strip().lower() in LOCAL_SOURCES


def _chain(client: Any) -> list[Any]:
    inner = getattr(client, "clients", None)
    return list(inner) if inner else [client]


def gate(client: Any, estimated_tokens: int) -> Any:
    """Bütçe kapısı istemci zincirine uygulanır (bütçe dolunca kilit yalnız ücretlilere).

    Zincirde ücretli sağlayıcı yoksa ya da bütçe yetiyorsa zincir aynen döner. Bütçe
    dolduysa ücretli sağlayıcılar çıkarılır: geriye yerel model kalırsa onunla devam
    edilir (sohbet kilitlenmez), hiç kalmazsa None (bütçe aşıldı)."""
    if client is None:
        return None
    chain = _chain(client)
    if all(is_local(getattr(c, "name", None)) for c in chain) or can_spend(estimated_tokens):
        return client
    local = [c for c in chain if is_local(getattr(c, "name", None))]
    if not local:
        return None
    if len(local) == 1:
        return local[0]
    from packages.agent.llm.client import FallbackLLMClient

    return FallbackLLMClient(local)


def can_spend(estimated_tokens: int) -> bool:
    return used_tokens() + max(0, int(estimated_tokens)) <= daily_budget()


def record(used: int, source: str | None = None) -> None:
    """Kullanımı ortak bütçeye yaz — cevabı yerel model verdiyse YAZILMAZ (ücretsiz)."""
    if is_local(source):
        return
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
