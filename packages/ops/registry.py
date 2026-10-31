"""Model, sinyal ve ajan kaydı (hedef mimari: st_registry) — sürümler tek yerden.

Kod commit'i, yapılandırma ve ağırlık özetleri, karar bayrakları, YZ modelleri,
talimat sürümleri, öğrenme motoru sürümleri ve terfi/geri alma geçmişi tek sözlükte. Karar kaydının
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


_HISTORY_SOURCES = {
    "weights": ("packages.learning.rebalance_store", "history"),
    "tf_targets": ("packages.learning.tf_target_rollback", "history"),
    "guards": ("packages.learning.guard_monitor_store", "history"),
}


def history(limit: int = 10) -> dict[str, list[dict]]:
    """Terfi ve geri alma geçmişi (en yeni önce): ağırlık önerileri, TF hedef
    ayarları, koruma izlemeleri ve bayrak etkinleştirme izleyicisi."""
    import importlib

    out: dict[str, list[dict]] = {}
    for key, (module, fn) in _HISTORY_SOURCES.items():
        try:
            out[key] = list(getattr(importlib.import_module(module), fn)(limit))
        except Exception:
            out[key] = []
    try:
        from packages.learning import activation_watchdog

        out["flags"] = list((activation_watchdog.report().get("history") or [])[:limit])
    except Exception:
        out["flags"] = []
    return out


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
        "history": history(),
    }


__all__ = ["history", "snapshot"]
