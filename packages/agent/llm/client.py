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
import re
import urllib.error
import urllib.request
from collections.abc import Iterator
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


# Streaming sözleşmesi: ("delta", str) parçaları, ardından ("done", LLMCompletion).
# Hata İLK parçadan önce olursa generator hiç yield etmeden biter (caller fallback'e
# geçebilir); parça geldikten SONRA koparsa "done"suz biter (kesinti sinyali).
StreamEvent = tuple[str, "str | LLMCompletion"]

ChatMessage = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": str}


def _iter_openai_sse(
    resp, default_model: str, source: str
) -> Iterator[StreamEvent]:
    """OpenAI-uyumlu SSE gövdesini (Groq/OpenRouter) StreamEvent'lere çevirir.

    `resp.read()` KULLANILMAZ — satır satır okunur (chunked'ı http.client çözer).
    Usage, sağlayıcıya göre son chunk'ta `usage` ya da `x_groq.usage` altında gelir;
    yoksa 0 kalır (caller tahmin eder).
    """
    text_parts: list[str] = []
    model = default_model
    input_tokens = 0
    output_tokens = 0
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        usage = data.get("usage") or (data.get("x_groq") or {}).get("usage") or {}
        if usage:
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
        model = str(data.get("model") or model)
        choices = data.get("choices") or []
        delta = ""
        if choices:
            delta = ((choices[0] or {}).get("delta") or {}).get("content") or ""
        if delta:
            text_parts.append(delta)
            yield ("delta", delta)
    full = "".join(text_parts).strip()
    if full:
        yield (
            "done",
            LLMCompletion(
                text=full,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                source=source,
            ),
        )


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

    def complete(
        self, system: str, user: str, max_tokens: int, temperature: float = 0.2
    ) -> LLMCompletion | None:
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

    def stream(
        self, messages: list[ChatMessage], max_tokens: int, temperature: float = 0.2
    ) -> Iterator[StreamEvent]:
        """Deterministik 3 parçalı stream — testler delta birleşimi == done.text doğrular."""
        user = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        head = user.strip().splitlines()[0][:120] if user.strip() else ""
        text = f"[mock-llm] {head}"
        third = max(1, len(text) // 3)
        chunks = [text[:third], text[third : 2 * third], text[2 * third :]]
        for chunk in chunks:
            if chunk:
                yield ("delta", chunk)
        yield (
            "done",
            LLMCompletion(
                text=text,
                model=self.model,
                input_tokens=sum(len(m.get("content", "")) for m in messages) // 4,
                output_tokens=len(text) // 4,
                source="mock",
            ),
        )


class GroqClient:
    """Groq OpenAI-uyumlu chat completions adapter'ı."""

    name = "groq"

    def __init__(self) -> None:
        _load_repo_dotenv_once()
        self.api_key = os.environ.get("GROQ_API_KEY", "").strip()
        self.model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()

    def complete(
        self, system: str, user: str, max_tokens: int, temperature: float = 0.2
    ) -> LLMCompletion | None:
        if not self.api_key:
            return None  # anahtar yok → network çağrısı yok
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": int(max_tokens),
                "temperature": float(temperature),
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

    def stream(
        self, messages: list[ChatMessage], max_tokens: int, temperature: float = 0.2
    ) -> Iterator[StreamEvent]:
        if not self.api_key:
            return
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": int(max_tokens),
                "temperature": float(temperature),
                "stream": True,
                "messages": messages,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            GROQ_API_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "clean-e-yay/2.7",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT_SEC)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return  # ilk parça öncesi hata → hiç yield yok, caller fallback'e geçer
        try:
            yield from _iter_openai_sse(resp, self.model, "groq")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return  # akış ortası kesinti → "done"suz biter
        finally:
            resp.close()


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

    def _request(
        self, system: str, user: str, max_tokens: int, temperature: float = 0.2
    ) -> urllib.request.Request:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": int(max_tokens),
                "temperature": float(temperature),
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
        return urllib.request.Request(self.api_url, data=body, headers=headers, method="POST")

    def complete(
        self, system: str, user: str, max_tokens: int, temperature: float = 0.2
    ) -> LLMCompletion | None:
        if not self.api_key:
            return None  # anahtar yok → network çağrısı yok
        attempt_tokens = int(max_tokens)
        # 402 (yetersiz kredi) → hesabın o anda "karşılayabildiği" token sayısına
        # düşüp BİR kez yeniden dene. Düşük bakiyede de chat çalışsın diye;
        # kredi tamamen biterse zaten son denemede de None döner (fallback devreye girer).
        for _ in range(2):
            req = self._request(system, user, attempt_tokens, temperature)
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
            except urllib.error.HTTPError as e:
                if e.code == 402:
                    try:
                        err = json.loads(e.read().decode("utf-8"))
                        msg = str((err.get("error") or {}).get("message") or "")
                        m = re.search(r"can only afford (\d+)", msg)
                        affordable = int(m.group(1)) if m else None
                    except (ValueError, TypeError, json.JSONDecodeError, AttributeError):
                        affordable = None
                    if affordable and affordable > 16 and affordable < attempt_tokens:
                        attempt_tokens = affordable - 8  # küçük güvenlik payı
                        continue
                return None
            except (urllib.error.URLError, TimeoutError, OSError, KeyError,
                    IndexError, TypeError, ValueError):
                return None  # crash yok — fallback narrative devreye girer
        return None

    def stream(
        self, messages: list[ChatMessage], max_tokens: int, temperature: float = 0.2
    ) -> Iterator[StreamEvent]:
        if not self.api_key:
            return
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": int(max_tokens),
                "temperature": float(temperature),
                "stream": True,
                "messages": messages,
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "clean-e-yay/2.7",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.app_name:
            headers["X-OpenRouter-Title"] = self.app_name
        req = urllib.request.Request(self.api_url, data=body, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT_SEC)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return
        try:
            yield from _iter_openai_sse(resp, self.model, "openrouter")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return
        finally:
            resp.close()


class OllamaClient:
    """Local Ollama chat adapter; no API key required.

    Remote API'lerden farklı: local CPU inference YAVAŞ (7B soğuk yükleme ~15s +
    üretim). Bu yüzden ayrı, uzun timeout (OLLAMA_TIMEOUT_SEC, default 120s) ve
    keep_alive (modeli RAM'de tutar → sonraki isteklerde soğuk yükleme yok). Genel
    12s TIMEOUT_SEC burada kullanılsa her istek timeout olurdu."""

    name = "ollama"

    def __init__(self) -> None:
        _load_repo_dotenv_once()
        self.model = os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()
        self.api_url = os.environ.get("OLLAMA_API_URL", OLLAMA_API_URL).strip()
        try:
            self.timeout = float(os.environ.get("OLLAMA_TIMEOUT_SEC", "120"))
        except (TypeError, ValueError):
            self.timeout = 120.0
        # Modeli RAM'de tut → soğuk yükleme (ilk istekteki ~15s) tekrar etmesin.
        self.keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "30m").strip()

    def complete(
        self, system: str, user: str, max_tokens: int, temperature: float = 0.2
    ) -> LLMCompletion | None:
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "keep_alive": self.keep_alive,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "options": {
                    "temperature": float(temperature),
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
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
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

    def stream(
        self, messages: list[ChatMessage], max_tokens: int, temperature: float = 0.2
    ) -> Iterator[StreamEvent]:
        """Ollama NDJSON stream'i — her satır bir JSON; final satır done:true + usage."""
        body = json.dumps(
            {
                "model": self.model,
                "stream": True,
                "keep_alive": self.keep_alive,
                "messages": messages,
                "options": {
                    "temperature": float(temperature),
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
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return
        text_parts: list[str] = []
        model = self.model
        input_tokens = 0
        output_tokens = 0
        try:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                model = str(data.get("model") or model)
                msg = data.get("message") or {}
                delta = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(delta, str) and delta:
                    text_parts.append(delta)
                    yield ("delta", delta)
                if data.get("done"):
                    input_tokens = int(data.get("prompt_eval_count") or 0)
                    output_tokens = int(data.get("eval_count") or 0)
                    break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return
        finally:
            resp.close()
        full = "".join(text_parts).strip()
        if full:
            yield (
                "done",
                LLMCompletion(
                    text=full,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    source="ollama",
                ),
            )


class FallbackLLMClient:
    """Try LLM clients in order; used for Ollama local-first mode."""

    name = "fallback"

    def __init__(self, clients: list[MockLLMClient | GroqClient | OpenRouterClient | OllamaClient]) -> None:
        self.clients = clients
        self.model = " -> ".join(c.model for c in clients)

    def complete(
        self, system: str, user: str, max_tokens: int, temperature: float = 0.2
    ) -> LLMCompletion | None:
        for client in self.clients:
            comp = client.complete(system, user, max_tokens, temperature)
            if comp is not None:
                return comp
        return None

    def stream(
        self, messages: list[ChatMessage], max_tokens: int, temperature: float = 0.2
    ) -> Iterator[StreamEvent]:
        """Sırayla dene; bir client İLK event'ini verdiyse artık ona kilitlen.

        İlk parça kullanıcıya gösterildikten sonra client değiştirmek metni
        karıştırır — kesinti olursa "done"suz biter, caller grounded'a döner.
        Hiç yield etmeden biten client (anahtar yok / bağlantı hatası) atlanır.
        """
        for client in self.clients:
            yielded = False
            for event in client.stream(messages, max_tokens, temperature):
                yielded = True
                yield event
            if yielded:
                return


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


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def get_chat_client() -> MockLLMClient | GroqClient | OpenRouterClient | OllamaClient | FallbackLLMClient | None:
    """Chat (canlı panel) için client — persona raporlarından FARKLI sıra.

    Ollama modunda default Groq-önce ([Groq?, OpenRouter?, Ollama]): chat'te hız +
    kalite birincil, lokal 7B model yedek (owner kararı 2026-07-03).
    CHAT_LLM_LOCAL_FIRST=1 eski lokal-önce sıraya döndürür. Persona raporları
    get_client() ile aynen lokal-önce kalır.
    """
    mode = get_mode()
    if mode != "ollama":
        return get_client()
    if _truthy_env("CHAT_LLM_LOCAL_FIRST"):
        return FallbackLLMClient([OllamaClient(), *_remote_fallback_clients()])
    clients: list[GroqClient | OpenRouterClient | OllamaClient] = []
    groq = GroqClient()
    if groq.api_key:
        clients.append(groq)
    openrouter = OpenRouterClient()
    if openrouter.api_key:
        clients.append(openrouter)
    clients.append(OllamaClient())
    return FallbackLLMClient(clients)
