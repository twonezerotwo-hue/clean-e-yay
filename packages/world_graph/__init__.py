"""Versioned, evidence-only global topology graph."""

from packages.world_graph.engine import build_context, load_graph
from packages.world_graph.model import WorldGraphContext

__all__ = ["WorldGraphContext", "build_context", "load_graph"]
