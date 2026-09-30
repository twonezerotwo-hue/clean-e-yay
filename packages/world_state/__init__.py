"""Deterministic world-state evidence layer (shadow-only by default)."""

from packages.world_state.engine import build
from packages.world_state.model import (
    GeopoliticalEvent,
    MacroSurpriseImpact,
    PolicyStatement,
    WorldStateSnapshot,
)

__all__ = ["GeopoliticalEvent", "MacroSurpriseImpact", "PolicyStatement", "WorldStateSnapshot", "build"]
