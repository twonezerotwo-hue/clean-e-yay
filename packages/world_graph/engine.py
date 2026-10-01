"""Load and resolve a bounded global knowledge graph.

The graph is topology, not a live news feed.  Current severity and confidence
still come only from verified snapshot events.  Resolver output is evidence
for the world-state layer and never a trade decision.
"""
from __future__ import annotations

import os
import re
from collections import deque
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from packages.world_graph.model import (
    WorldEntity,
    WorldGraph,
    WorldGraphContext,
    WorldRelation,
)

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "world_graph_v1.0.yaml"
_MAX_MATCHES = 32
_MAX_PATHS = 64
_MAX_DEPTH = 2


def _path() -> Path:
    raw = os.environ.get("WORLD_GRAPH_CONFIG_PATH", str(_DEFAULT_PATH))
    return Path(raw) if Path(raw).is_absolute() else Path(__file__).resolve().parents[2] / raw


def _text(value: Any) -> str:
    return str(value or "").casefold().strip()


def _weight(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def load_graph() -> WorldGraph:
    """Read and validate the graph on each call so owner edits are restart-safe."""
    raw = yaml.safe_load(_path().read_text(encoding="utf-8")) or {}
    version = str(raw.get("version") or "world-graph-unknown")
    entities: list[WorldEntity] = []
    seen: set[str] = set()
    for item in raw.get("entities") or ():
        if not isinstance(item, Mapping):
            continue
        entity_id = str(item.get("id") or "").strip()
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        aliases = tuple(dict.fromkeys(_text(x) for x in (item.get("aliases") or ()) if _text(x)))
        name = str(item.get("name") or entity_id)
        entities.append(WorldEntity(entity_id, str(item.get("type") or "UNKNOWN").upper(), name, aliases, dict(item.get("attributes") or {})))
    entity_ids = {item.entity_id for item in entities}
    relations: list[WorldRelation] = []
    for item in raw.get("relations") or ():
        if not isinstance(item, Mapping):
            continue
        source, target = str(item.get("source") or ""), str(item.get("target") or "")
        if source not in entity_ids or target not in entity_ids:
            continue
        relations.append(WorldRelation(source, str(item.get("relation") or "RELATED_TO").upper(), target, _weight(item.get("weight", 1.0))))
    return WorldGraph(version, tuple(entities), tuple(relations))


def _event_text(event: Any) -> str:
    if isinstance(event, Mapping):
        values = [event.get(key) for key in ("event_id", "event_type", "region", "location", "title", "text")]
        values.append(" ".join(str(x) for x in (event.get("actors") or ()) ))
    else:
        values = [getattr(event, key, None) for key in ("event_id", "event_type", "region", "location", "title", "text", "actors")]
    return " ".join(str(value or "") for value in values).casefold()


def _match_entities(graph: WorldGraph, event: Any) -> list[WorldEntity]:
    text = _event_text(event)
    if not text:
        return []
    matched: list[WorldEntity] = []
    for entity in graph.entities:
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text) for alias in entity.aliases):
            matched.append(entity)
        if len(matched) >= _MAX_MATCHES:
            break
    return matched


def build_context(events: Iterable[Any] = (), *, graph: WorldGraph | None = None) -> WorldGraphContext:
    """Resolve event mentions into bounded topology paths and asset channels."""
    if graph is None:
        try:
            graph = load_graph()
        except (OSError, TypeError, ValueError, yaml.YAMLError):
            return WorldGraphContext(
                graph_version="unavailable",
                warnings=("world_graph_unavailable",),
            )
    adjacency: dict[str, list[WorldRelation]] = {}
    for relation in graph.relations:
        adjacency.setdefault(relation.source, []).append(relation)
    all_ids: set[str] = set()
    paths: list[dict[str, Any]] = []
    affected_assets: set[str] = set()
    channels: set[str] = set()
    event_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for event in events or ():
        matched = _match_entities(graph, event)
        event_id = str((event.get("event_id") if isinstance(event, Mapping) else getattr(event, "event_id", None)) or "")
        if not matched:
            event_rows.append({"event_id": event_id, "matched_entity_ids": [], "status": "NO_MATCH"})
            warnings.append(f"graph_no_entity_match:{event_id or 'unknown'}")
            continue
        row_paths: list[dict[str, Any]] = []
        for root in matched:
            queue: deque[tuple[str, tuple[str, ...], tuple[str, ...], float]] = deque([(root.entity_id, (root.entity_id,), (), 1.0)])
            seen: set[tuple[str, int]] = set()
            while queue and len(paths) + len(row_paths) < _MAX_PATHS:
                current, node_path, relation_path, confidence = queue.popleft()
                depth = len(relation_path)
                all_ids.add(current)
                entity = next(item for item in graph.entities if item.entity_id == current)
                attrs = entity.attributes or {}
                affected_assets.update(str(x) for x in attrs.get("asset_symbols") or ())
                channels.update(str(x) for x in attrs.get("factor_channels") or ())
                if depth:
                    path = {"event_id": event_id, "entity_ids": list(node_path), "relations": list(relation_path), "confidence": round(confidence, 4)}
                    row_paths.append(path)
                if depth >= _MAX_DEPTH:
                    continue
                marker = (current, depth)
                if marker in seen:
                    continue
                seen.add(marker)
                for relation in adjacency.get(current, ()):
                    queue.append((relation.target, (*node_path, relation.target), (*relation_path, relation.relation), confidence * relation.weight))
        paths.extend(row_paths[: max(0, _MAX_PATHS - len(paths))])
        event_rows.append({"event_id": event_id, "matched_entity_ids": [item.entity_id for item in matched], "status": "MATCHED", "path_count": len(row_paths)})
    if len(paths) >= _MAX_PATHS:
        warnings.append("graph_path_limit_reached")
    return WorldGraphContext(
        graph_version=graph.version,
        event_matches=tuple(event_rows),
        entity_ids=tuple(sorted(all_ids)),
        paths=tuple(paths[:_MAX_PATHS]),
        affected_assets=tuple(sorted(affected_assets)),
        factor_channels=tuple(sorted(channels)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = ["build_context", "load_graph"]
