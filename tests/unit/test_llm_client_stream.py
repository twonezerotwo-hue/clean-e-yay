"""v2.8 — LLM client streaming adapter testleri.

Hard kurallar:
- Testlerde network çağrısı YOK (urlopen patch'lenir / no_network bekçi).
- Stream sözleşmesi: ("delta", str)* → ("done", LLMCompletion). İlk parça öncesi
  hata → hiç yield yok; parça sonrası kesinti → "done"suz biter.
- Fallback: hiç yield etmeyen client atlanır; ilk yield'den sonra kilitlenilir.
- get_chat_client: ollama modunda default Groq-önce; CHAT_LLM_LOCAL_FIRST=1 eski sıra.
"""
from __future__ import annotations

import io
import json
import urllib.request

import pytest


@pytest.fixture
def llm_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "budget.json"))
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("LLM_LOAD_DOTENV", "false")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODE", raising=False)
    return tmp_path


_MESSAGES = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "soru"},
]


def _sse_body(*payloads: str) -> io.BytesIO:
    lines = []
    for p in payloads:
        lines.append(f"data: {p}\n".encode())
        lines.append(b"\n")
    return io.BytesIO(b"".join(lines))


# ---------- Groq / OpenAI-uyumlu SSE parser ----------

def test_groq_stream_parses_deltas_and_usage(llm_env, monkeypatch) -> None:
    from packages.agent.llm import client as llm_client

    monkeypatch.setenv("LLM_MODE", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    body = _sse_body(
        json.dumps({"model": "llama-3.3-70b-versatile",
                    "choices": [{"delta": {"content": "Merhaba"}}]}),
        json.dumps({"choices": [{"delta": {"content": " dunya"}}]}),
        json.dumps({"choices": [{"delta": {}}],
                    "x_groq": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}}),
        "[DONE]",
    )
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: body)

    events = list(llm_client.GroqClient().stream(_MESSAGES, 100))
    deltas = [p for k, p in events if k == "delta"]
    dones = [p for k, p in events if k == "done"]
    assert deltas == ["Merhaba", " dunya"]
    assert len(dones) == 1
    assert dones[0].text == "Merhaba dunya"
    assert dones[0].input_tokens == 10 and dones[0].output_tokens == 5
    assert dones[0].source == "groq"


def test_groq_stream_no_key_yields_nothing_no_network(llm_env, monkeypatch) -> None:
    from packages.agent.llm import client as llm_client

    def _boom(*a, **k):
        raise AssertionError("network call attempted in test")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert list(llm_client.GroqClient().stream(_MESSAGES, 100)) == []


def test_groq_stream_connection_error_yields_nothing(llm_env, monkeypatch) -> None:
    from packages.agent.llm import client as llm_client

    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def _fail(*a, **k):
        raise urllib.error.URLError("boom")

    import urllib.error

    monkeypatch.setattr(urllib.request, "urlopen", _fail)
    assert list(llm_client.GroqClient().stream(_MESSAGES, 100)) == []


# ---------- Ollama NDJSON ----------

def test_ollama_stream_parses_ndjson(llm_env, monkeypatch) -> None:
    from packages.agent.llm import client as llm_client

    lines = [
        json.dumps({"model": "llama3.1:8b", "message": {"content": "Selam"}, "done": False}),
        json.dumps({"message": {"content": " patron"}, "done": False}),
        json.dumps({"done": True, "prompt_eval_count": 7, "eval_count": 3}),
    ]
    body = io.BytesIO(("\n".join(lines) + "\n").encode())
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: body)

    events = list(llm_client.OllamaClient().stream(_MESSAGES, 100))
    deltas = [p for k, p in events if k == "delta"]
    dones = [p for k, p in events if k == "done"]
    assert deltas == ["Selam", " patron"]
    assert len(dones) == 1
    assert dones[0].text == "Selam patron"
    assert dones[0].input_tokens == 7 and dones[0].output_tokens == 3
    assert dones[0].source == "ollama"


# ---------- Mock stream ----------

def test_mock_stream_delta_concat_equals_done_text(llm_env) -> None:
    from packages.agent.llm import client as llm_client

    events = list(llm_client.MockLLMClient().stream(_MESSAGES, 100))
    deltas = [p for k, p in events if k == "delta"]
    dones = [p for k, p in events if k == "done"]
    assert len(dones) == 1
    assert "".join(deltas) == dones[0].text
    assert dones[0].source == "mock"


# ---------- Fallback sırası ----------

class _SilentClient:
    """Hiç yield etmeyen client (anahtar yok / bağlantı hatası)."""

    name = "silent"
    model = "silent"

    def stream(self, messages, max_tokens, temperature=0.2):
        return iter(())


class _DyingClient:
    """İlk parçadan sonra ölen client — done gelmez (kesinti)."""

    name = "dying"
    model = "dying"

    def stream(self, messages, max_tokens, temperature=0.2):
        yield ("delta", "yarim ")


def test_fallback_stream_skips_silent_client(llm_env) -> None:
    from packages.agent.llm import client as llm_client

    fb = llm_client.FallbackLLMClient([_SilentClient(), llm_client.MockLLMClient()])
    events = list(fb.stream(_MESSAGES, 100))
    assert [k for k, _ in events][-1] == "done"
    assert any(k == "delta" for k, _ in events)


def test_fallback_stream_locks_after_first_yield(llm_env) -> None:
    from packages.agent.llm import client as llm_client

    # İlk client parça verdikten sonra ölürse SONRAKİNE GEÇİLMEZ — metin
    # karışmasın; caller "done"suz bitişi kesinti sayar.
    fb = llm_client.FallbackLLMClient([_DyingClient(), llm_client.MockLLMClient()])
    events = list(fb.stream(_MESSAGES, 100))
    assert events == [("delta", "yarim ")]


# ---------- get_chat_client sırası ----------

def test_chat_client_ollama_mode_default_groq_first(llm_env, monkeypatch) -> None:
    from packages.agent.llm import client as llm_client

    monkeypatch.setenv("LLM_MODE", "ollama")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or")
    c = llm_client.get_chat_client()
    assert isinstance(c, llm_client.FallbackLLMClient)
    kinds = [type(x).__name__ for x in c.clients]
    assert kinds == ["GroqClient", "OpenRouterClient", "OllamaClient"]


def test_chat_client_local_first_flag_restores_old_order(llm_env, monkeypatch) -> None:
    from packages.agent.llm import client as llm_client

    monkeypatch.setenv("LLM_MODE", "ollama")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("CHAT_LLM_LOCAL_FIRST", "1")
    c = llm_client.get_chat_client()
    assert isinstance(c, llm_client.FallbackLLMClient)
    assert type(c.clients[0]).__name__ == "OllamaClient"


def test_chat_client_non_ollama_modes_delegate(llm_env, monkeypatch) -> None:
    from packages.agent.llm import client as llm_client

    monkeypatch.setenv("LLM_MODE", "off")
    assert llm_client.get_chat_client() is None
    monkeypatch.setenv("LLM_MODE", "mock")
    assert isinstance(llm_client.get_chat_client(), llm_client.MockLLMClient)


def test_persona_client_order_unchanged_by_chat_flag(llm_env, monkeypatch) -> None:
    from packages.agent.llm import client as llm_client

    # Persona raporları (get_client) HER ZAMAN lokal-önce kalır — chat flag'i
    # onları etkilemez.
    monkeypatch.setenv("LLM_MODE", "ollama")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    c = llm_client.get_client()
    assert isinstance(c, llm_client.FallbackLLMClient)
    assert type(c.clients[0]).__name__ == "OllamaClient"
