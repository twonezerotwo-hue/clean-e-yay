"""LLM provider abstraction — LLM_MODE=off|mock|groq|openrouter|ollama.

Kurallar:
- Anahtar yoksa (groq/openrouter modunda) network çağrısı YAPILMAZ → None döner.
- Ollama local-first'tir; çalışmazsa openrouter/groq fallback denenebilir.
- Network/API hatası exception KAÇIRMAZ → None döner (graceful degrade).
- Çağıran taraf None'ı deterministik fallback narrative ile karşılar.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_OPENROUTER_MODEL = "~openai/gpt-latest"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
TIMEOUT_SEC = 12.0
_DOTENV_LOADED = False


def _load_repo_dotenv_once() -> None:
    """Root .env'i yalnızca eksik env'ler için yükle; shell env override edilmez."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    if os.environ.get("LLM_LOAD_DOTENV", "true").strip().lower() in {"0", "false", "no"}:
        return
    path = Path(__file__).resolve().parents[3] / ".env"
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return


@dataclass
class LLMCompletion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    source: str  # "groq" | "openrouter" | "ollama" | "mock"


def get_mode() -> str:
    """off|mock|groq|openrouter|ollama — env LLM_MODE; set değilse anahtara göre auto."""
    _load_repo_dotenv_once()
    mode = (os.environ.get("LLM_MODE") or "").strip().lower()
    if mode in {"off", "mock", "groq", "openrouter", "ollama"}:
        return mode
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    return "groq" if os.environ.get("GROQ_API_KEY") else "off"


class MockLLMClient:
    """Deterministik test/dev client'ı — network yok."""

    name = "mock"
    model = "mock-llm"

    def complete(self, system: str, user: str, max_tokens: int) -> LLMCompletion | None:
        # Deterministik, prompt'a bağlı kısa çıktı — testler içerik değil
        # akış (fallback vs llm) doğrular.
        head = user.strip().splitlines()[0][:120] if user.strip() else ""
        text = f"[mock-llm] {head}"
        return LLMCompletion(
            text=text,
            model=self.model,
            input_tokens=(len(system) + len(user)) // 4,
            output_tokens=len(text) // 4,
            source="mock",
        )


class GroqClient:
    """Groq OpenAI-uyumlu chat completions adapter'ı."""

    name = "groq"

    def __init__(self) -> None:
        _load_repo_dotenv_once()
        self.api_key = os.environ.get("GROQ_API_KEY", "").strip()
        self.model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()

    def complete(self, system: str, user: str, max_tokens: int) -> LLMCompletion | None:
        if not self.api_key:
            return None  # anahtar yok → network çağrısı yok
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": int(max_tokens),
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            GROQ_API_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "clean-e-yay/2.6",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            if not isinstance(text, str) or not text.strip():
                return None
            return LLMCompletion(
                text=text.strip(),
                model=str(data.get("model") or self.model),
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                source="groq",
            )
        except (urllib.error.URLError, TimeoutError, OSError, KeyError,
                IndexError, TypeError, ValueError):
            return None  # crash yok — fallback narrative devreye girer


class OpenRouterClient:
    """OpenRouter OpenAI-uyumlu chat completions adapter'ı."""

    name = "openrouter"

    def __init__(self) -> None:
        _load_repo_dotenv_once()
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.model = os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip()
        self.api_url = os.environ.get("OPENROUTER_API_URL", OPENROUTER_API_URL).strip()
        self.site_url = os.environ.get("OPENROUTER_SITE_URL", "").strip()
        self.app_name = os.environ.get("OPENROUTER_APP_NAME", "Clean E-yAy").strip()

    def complete(self, system: str, user: str, max_tokens: int) -> LLMCompletion | None:
        if not self.api_key:
            return None  # anahtar yok → network çağrısı yok
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": int(max_tokens),
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "clean-e-yay/2.6",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.app_name:
            headers["X-OpenRouter-Title"] = self.app_name
        req = urllib.request.Request(
            self.api_url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            if not isinstance(text, str) or not text.strip():
                return None
            return LLMCompletion(
                text=text.strip(),
                model=str(data.get("model") or self.model),
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                source="openrouter",
            )
        except (urllib.error.URLError, TimeoutError, OSError, KeyError,
                IndexError, TypeError, ValueError):
            return None  # crash yok — fallback narrative devreye girer


class OllamaClient:
    """Local Ollama chat adapter; no API key required."""

    name = "ollama"

    def __init__(self) -> None:
        _load_repo_dotenv_once()
        self.model = os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()
        self.api_url = os.environ.get("OLLAMA_API_URL", OLLAMA_API_URL).strip()

    def complete(self, system: str, user: str, max_tokens: int) -> LLMCompletion | None:
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "options": {
                    "temperature": 0.2,
                    "num_predict": int(max_tokens),
                },
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.api_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "clean-e-yay/2.7",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            msg = data.get("message") or {}
            text = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(text, str) or not text.strip():
                return None
            return LLMCompletion(
                text=text.strip(),
                model=str(data.get("model") or self.model),
                input_tokens=int(data.get("prompt_eval_count") or 0),
                output_tokens=int(data.get("eval_count") or 0),
                source="ollama",
            )
        except (urllib.error.URLError, TimeoutError, OSError, KeyError,
                TypeError, ValueError, json.JSONDecodeError):
            return None


class FallbackLLMClient:
    """Try LLM clients in order; used for Ollama local-first mode."""

    name = "fallback"

    def __init__(self, clients: list[MockLLMClient | GroqClient | OpenRouterClient | OllamaClient]) -> None:
        self.clients = clients
        self.model = " -> ".join(c.model for c in clients)

    def complete(self, system: str, user: str, max_tokens: int) -> LLMCompletion | None:
        for client in self.clients:
            comp = client.complete(system, user, max_tokens)
            if comp is not None:
                return comp
        return None


def _remote_fallback_clients() -> list[OpenRouterClient | GroqClient]:
    clients: list[OpenRouterClient | GroqClient] = []
    openrouter = OpenRouterClient()
    if openrouter.api_key:
        clients.append(openrouter)
    groq = GroqClient()
    if groq.api_key:
        clients.append(groq)
    return clients


def get_client() -> MockLLMClient | GroqClient | OpenRouterClient | OllamaClient | FallbackLLMClient | None:
    """Aktif mod için client; off (veya anahtarsız remote) → None."""
    mode = get_mode()
    if mode == "mock":
        return MockLLMClient()
    if mode == "groq":
        c = GroqClient()
        return c if c.api_key else None
    if mode == "openrouter":
        c = OpenRouterClient()
        return c if c.api_key else None
    if mode == "ollama":
        return FallbackLLMClient([OllamaClient(), *_remote_fallback_clients()])
    return None
