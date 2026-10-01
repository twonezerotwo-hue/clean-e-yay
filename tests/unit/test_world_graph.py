from __future__ import annotations

from packages.world_graph import build_context, load_graph


def test_world_graph_loads_versioned_topology_and_expands_bab_el_mandeb():
    graph = load_graph()
    assert graph.version == "world-graph-v1.0"
    assert any(entity.entity_id == "chokepoint:bab_el_mandeb" for entity in graph.entities)
    context = build_context([{
        "event_id": "geo-1",
        "event_type": "CHOKEPOINT_THREAT",
        "title": "Yemen Houthi threat near Bab el-Mandeb disrupts Red Sea shipping",
        "region": "Red Sea",
    }], graph=graph)
    assert context.event_matches[0]["status"] == "MATCHED"
    assert "BRENT" in context.affected_assets
    assert "shipping_risk" in context.factor_channels
    assert any("CONNECTS" in path["relations"] for path in context.paths)


def test_world_graph_does_not_invent_match_for_unknown_event():
    context = build_context([{"event_id": "unknown", "title": "A local event without topology terms"}])
    assert context.event_matches[0]["status"] == "NO_MATCH"
    assert context.affected_assets == ()
    assert "graph_no_entity_match:unknown" in context.warnings


def test_world_graph_failure_is_observation_only(monkeypatch):
    monkeypatch.setenv("WORLD_GRAPH_CONFIG_PATH", "C:/does-not-exist/world-graph.yaml")
    context = build_context([{"event_id": "x", "title": "Bab el-Mandeb"}])
    assert context.graph_version == "unavailable"
    assert context.warnings == ("world_graph_unavailable",)

