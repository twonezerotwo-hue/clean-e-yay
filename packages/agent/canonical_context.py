"""Single canonical LLM context package.

The implementation remains in ``agent.llm.context`` for compatibility; this
stable package name is now the only import surface used by API chat/report
consumers. It prevents panels from constructing ad-hoc prompt payloads.
"""
from __future__ import annotations

from packages.agent.llm.context import (
    _humanize_gate,
    build_compact_context,
    context_digest,
    context_for_prompt,
    no_actionable_decision,
)

SCHEMA_VERSION = 1


def build_canonical_context() -> dict:
    context = build_compact_context()
    context["schema_version"] = SCHEMA_VERSION
    context["canonical"] = True
    return context


__all__ = [
    "SCHEMA_VERSION",
    "_humanize_gate",
    "build_canonical_context",
    "context_digest",
    "context_for_prompt",
    "no_actionable_decision",
]
