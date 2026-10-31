"""Model, sinyal ve ajan kaydı (hedef mimari: st_registry) — sürümler tek yerden.

Kod commit'i, yapılandırma ve ağırlık özetleri, karar bayrakları, YZ modelleri,
talimat sürümleri ve öğrenme motoru sürümleri tek sözlükte. Karar kaydının
saatlik tam kopyası aynı `record.versions()` çekirdeğini taşır; bu modül onu
ajan ve öğrenme tarafıyla genişletir. Salt okuma.
"""
from __future__ import annotations

import os
from typing import Any

_LEARNING_ENGINES = (
    "council_scorecard", "exit_backtest", "reflection", "subsignal_scorecard",
    "tf_scoring_race", "zero_two_strategy", "zone_plan_shadow", "zone_proposer",
)


def snapshot() -> dict[str, Any]:
    import importlib

    from packages.agent.llm import chat, client
    from packages.data.registry.loader import active_weights_version
    from packages.decision import record

    core = record.versions()
    engines: dict[str, str | None] = {}
    for name in _LEARNING_ENGINES:
        try:
            engines[name] = getattr(importlib.import_module(f"packages.learning.{name}"), "_ENGINE", None)
        except Exception:
            engines[name] = None
    return {
        "code": core["commit"],
        "config": {"thresholds": core["thresholds"]},
        "weights": {"version": active_weights_version(), "digest": core["weights"]},
        "decision_flags": core["flags"],
        "models": {
            "groq": os.environ.get("GROQ_MODEL", client.DEFAULT_GROQ_MODEL).strip(),
            "openrouter": os.environ.get("OPENROUTER_MODEL", client.DEFAULT_OPENROUTER_MODEL).strip(),
            "ollama": os.environ.get("OLLAMA_MODEL", client.DEFAULT_OLLAMA_MODEL).strip(),
        },
        "prompts": {"chat": chat._PROMPT_VERSION},
        "learning_engines": engines,
    }


__all__ = ["snapshot"]
