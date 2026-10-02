"""Deterministic decision-trace helpers.

The trace is additive telemetry: it explains which inputs produced a decision but
does not alter score, sizing, RiskGate, or execution behaviour.  Timestamps are
deliberately excluded from the identity so a replay of the same closed snapshot
can be compared with the live observation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_decision_id(payload: dict[str, Any]) -> str:
    """Return a short deterministic id for a decision input/output bundle."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "dec_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def matrix_decision_id(
    *,
    symbol: str,
    risk_action: str | None,
    consensus: Any,
    decision: Any,
    economics: Any | None = None,
) -> str:
    """Identity for the read-only agent-matrix decision path.

    Only closed-bar decision inputs are included; generated timestamps are not.
    """
    econ = None
    if economics is not None:
        econ = {
            "allow": getattr(economics, "allow", None),
            "reason": getattr(economics, "reason", None),
            "rr": getattr(economics, "rr", None),
        }
    return stable_decision_id(
        {
            "path": "agent_matrix",
            "symbol": symbol,
            "risk_action": risk_action,
            "consensus": {
                "alignment_score": getattr(consensus, "alignment_score", None),
                "direction_score": getattr(consensus, "direction_score", None),
                "strength_score": getattr(consensus, "strength_score", None),
                "agreement_score": getattr(consensus, "agreement_score", None),
                "alignment_status": getattr(consensus, "alignment_status", None),
                "confirmed_count": getattr(consensus, "confirmed_count", None),
                "pending_count": getattr(consensus, "pending_count", None),
            },
            "decision": {
                "action": getattr(decision, "action", None),
                "entry_timeframe": getattr(decision, "entry_timeframe", None),
                "confidence": getattr(decision, "confidence", None),
                "size_multiplier": getattr(decision, "size_multiplier", None),
                "required_confirmations": list(
                    getattr(decision, "required_confirmations", None) or []
                ),
            },
            "economics": econ,
        }
    )


def matrix_confidence_breakdown(consensus: Any, decision: Any) -> dict[str, Any]:
    """Explain the matrix confidence without presenting it as p(win)."""
    alignment = float(getattr(consensus, "alignment_score", 0.0) or 0.0) / 100.0
    agreement = float(getattr(consensus, "agreement_score", 0.0) or 0.0) / 100.0
    return {
        "value": round(float(getattr(decision, "confidence", 0.0) or 0.0), 4),
        "source": "alignment_x_agreement",
        "alignment_component": round(max(0.0, min(1.0, alignment)), 4),
        "agreement_component": round(max(0.0, min(1.0, agreement)), 4),
        "strength_score": getattr(consensus, "strength_score", None),
        "is_win_probability": False,
        "book_evidence_applied": False,
    }


def book_evidence_status(evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Expose the book layer's promotion boundary in a compact trace field."""
    evidence = evidence or {}
    refs = evidence.get("references") or []
    return {
        "mode": evidence.get("mode", "unavailable"),
        "status": evidence.get("status", "UNAVAILABLE"),
        "reference_count": len(refs),
        "promoted_to_decision": bool(evidence.get("promoted_to_decision", False)),
        "applied": False,
    }


__all__ = [
    "book_evidence_status",
    "matrix_confidence_breakdown",
    "matrix_decision_id",
    "stable_decision_id",
]
