"""LLM provider abstraction — LLM_MODE=off|mock|groq.

Kurallar:
- Anahtar yoksa (groq modunda) network çağrısı YAPILMAZ → None döner.
- Network/API hatası exception KAÇIRMAZ → None döner (graceful degrade).
- Çağıran taraf None'ı deterministik fallback narrative ile karşılar.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
TIMEOUT_SEC = 12.0


@dataclass
class LLMCompletion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    source: str  # "groq" | "mock"


def get_mode() -> str:
    """off|mock|groq — env LLM_MODE; set değilse anahtar varsa groq, yoksa off."""
    mode = (os.environ.get("LLM_MODE") or "").strip().lower()
    if mode in {"off", "mock", "groq"}:
        return mode
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


def get_client() -> MockLLMClient | GroqClient | None:
    """Aktif mod için client; off (veya groq+anahtarsız) → None."""
    mode = get_mode()
    if mode == "mock":
        return MockLLMClient()
    if mode == "groq":
        c = GroqClient()
        return c if c.api_key else None
    return None
