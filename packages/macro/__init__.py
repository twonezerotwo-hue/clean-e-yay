"""Canonical macro evidence helpers.

The macro package is deliberately additive and shadow-only.  It gives news,
calendar, technical and causal consumers one evidence shape without granting
that shape authority over the existing decision or RiskGate paths.
"""

from packages.macro.evidence import build_macro_evidence

__all__ = ["build_macro_evidence"]
