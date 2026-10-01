"""Serializable models for the static global topology graph."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class WorldEntity:
    entity_id: str
    entity_type: str
    name: str
    aliases: tuple[str, ...] = ()
    attributes: dict[str, Any] | None = None


@dataclass(frozen=True)
class WorldRelation:
    source: str
    relation: str
    target: str
    weight: float = 1.0


@dataclass(frozen=True)
class WorldGraph:
    version: str
    entities: tuple[WorldEntity, ...]
    relations: tuple[WorldRelation, ...]


@dataclass(frozen=True)
class WorldGraphContext:
    """Bounded event expansion; not a current geopolitical truth claim."""

    graph_version: str
    event_matches: tuple[dict[str, Any], ...] = ()
    entity_ids: tuple[str, ...] = ()
    paths: tuple[dict[str, Any], ...] = ()
    affected_assets: tuple[str, ...] = ()
    factor_channels: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["WorldEntity", "WorldGraph", "WorldGraphContext", "WorldRelation"]
