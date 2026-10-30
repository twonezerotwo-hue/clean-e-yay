"""Canonical read-only decision lifecycle.

This module is deliberately a pure projection. It does not open/close paper
positions and it cannot bypass RiskGate. Every UI/LLM surface can therefore
describe the same state without inventing a second lifecycle.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class DecisionState(StrEnum):
    OBSERVED = "OBSERVED"
    TECHNICAL_CONFIRMED = "TECHNICAL_CONFIRMED"
    NEWS_CONFIRMED = "NEWS_CONFIRMED"
    CONFLUENCE_READY = "CONFLUENCE_READY"
    RISK_CHECKED = "RISK_CHECKED"
    PAPER_READY = "PAPER_READY"
    OWNER_APPROVAL = "OWNER_APPROVAL"
    PAPER_OPEN = "PAPER_OPEN"
    BLOCKED = "BLOCKED"


def derive_decision_state(
    cell: dict[str, Any],
    *,
    open_symbols: set[str] | None = None,
) -> tuple[str, str]:
    """Return one canonical lifecycle state and a human-readable reason."""
    open_symbols = open_symbols or set()
    symbol = str(cell.get("symbol") or "")
    if symbol in open_symbols:
        return DecisionState.PAPER_OPEN.value, "Aynı varlıkta açık paper pozisyon var."
    blockers = [str(x) for x in (cell.get("blocked_by") or [])]
    if cell.get("status") == "SUSPENDED" or blockers or cell.get("execution_state") == "BLOCKED":
        return DecisionState.BLOCKED.value, "; ".join(blockers[:3]) or "Risk/veri kapısı bekletiyor."
    if cell.get("final_execution_ready") or cell.get("execution_ready"):
        if cell.get("final_actionable") or cell.get("actionable"):
            return DecisionState.PAPER_READY.value, "Tüm kanıt ve RiskGate kontrolleri geçti."
        return DecisionState.OWNER_APPROVAL.value, "Paper açılışı için owner onayı bekleniyor."
    if cell.get("confluence_aligned") or cell.get("technical_confirmation"):
        return DecisionState.CONFLUENCE_READY.value, "Haber ve teknik kanıt aynı yöne hizalanıyor."
    if cell.get("direction") in {"bullish", "bearish"} or cell.get("score") not in (None, 50):
        return DecisionState.TECHNICAL_CONFIRMED.value, "Teknik yön var; nihai giriş kapıları bekleniyor."
    return DecisionState.OBSERVED.value, "Yalnızca izleme kanıtı mevcut."


__all__ = ["DecisionState", "derive_decision_state"]
