import pytest
from CodeGrapher.graph_index import GraphIndex


def test_empty_data_creates_empty_structures():
    """Empty data produces empty nodes_by_id, outgoing, and incoming dicts."""
    index = GraphIndex({})
    assert index.nodes_by_id == {}
    assert index.outgoing == {}
    assert index.incoming == {}


def test_nodes_only_no_edges():
    """Nodes without edges populates nodes_by_id and initializes outgoing/incoming."""
    data = {
        "nodes": [
            {"id": "a", "label": "Node A"},
            {"id": "b", "label": "Node B"},
        ],
        "edges": [],
    }
    index = GraphIndex(data)
    assert len(index.nodes_by_id) == 2
    assert index.nodes_by_id["a"]["label"] == "Node A"
    assert index.nodes_by_id["b"]["label"] == "Node B"
    assert index.outgoing["a"] == []
    assert index.outgoing["b"] == []
    assert index.incoming["a"] == []
    assert index.incoming["b"] == []


def test_get_node_hit():
    """get_node returns the node dict for a valid id."""
    data = {
        "nodes": [{"id": "node1", "label": "Test"}],
        "edges": [],
    }
    index = GraphIndex(data)
    node = index.get_node("node1")
    assert node is not None
    assert node["label"] == "Test"


def test_get_node_miss():
    """get_node returns None for unknown id."""
    index = GraphIndex({})
    assert index.get_node("nonexistent") is None


def test_edges_populate_outgoing_and_incoming():
    """Edges with valid from/to populate outgoing and incoming."""
    data = {
        "nodes": [
            {"id": "a"},
            {"id": "b"},
        ],
        "edges": [
            {"from": "a", "to": "b", "relation": "calls"},
        ],
    }
    index = GraphIndex(data)
    assert len(index.outgoing["a"]) == 1
    assert index.outgoing["a"][0]["to"] == "b"
    assert len(index.incoming["b"]) == 1
    assert index.incoming["b"][0]["from"] == "a"


def test_edges_with_missing_from_are_skipped():
    """Edges without 'from' field are skipped."""
    data = {
        "nodes": [{"id": "a"}],
        "edges": [
            {"to": "a", "relation": "calls"},
        ],
    }
    index = GraphIndex(data)
    assert index.outgoing["a"] == []
    assert index.incoming["a"] == []


def test_edges_with_missing_to_are_skipped():
    """Edges without 'to' field are skipped."""
    data = {
        "nodes": [{"id": "a"}],
        "edges": [
            {"from": "a", "relation": "calls"},
        ],
    }
    index = GraphIndex(data)
    assert index.outgoing["a"] == []
    assert index.incoming["a"] == []


def test_get_neighbors_direction_outgoing():
    """get_neighbors with direction='outgoing' returns only outgoing neighbors."""
    data = {
        "nodes": [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
        ],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "c", "to": "a"},
        ],
    }
    index = GraphIndex(data)
    neighbors = index.get_neighbors("a", direction="outgoing")
    assert len(neighbors) == 1
    assert neighbors[0]["id"] == "b"


def test_get_neighbors_direction_incoming():
    """get_neighbors with direction='incoming' returns only incoming neighbors."""
    data = {
        "nodes": [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
        ],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "c", "to": "a"},
        ],
    }
    index = GraphIndex(data)
    neighbors = index.get_neighbors("a", direction="incoming")
    assert len(neighbors) == 1
    assert neighbors[0]["id"] == "c"


def test_get_neighbors_direction_both():
    """get_neighbors with direction='both' returns union of incoming and outgoing."""
    data = {
        "nodes": [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
        ],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "c", "to": "a"},
        ],
    }
    index = GraphIndex(data)
    neighbors = index.get_neighbors("a", direction="both")
    ids = {n["id"] for n in neighbors}
    assert ids == {"b", "c"}


def test_get_neighbors_unknown_node():
    """get_neighbors for unknown node returns empty list."""
    data = {
        "nodes": [{"id": "a"}],
        "edges": [],
    }
    index = GraphIndex(data)
    neighbors = index.get_neighbors("nonexistent")
    assert neighbors == []


def test_node_referenced_only_in_edges():
    """Nodes referenced in edges but absent from nodes list: get_node returns None,
    but edges are still stored (dangling refs appear as sources in outgoing, targets in incoming)."""
    data = {
        "nodes": [{"id": "a"}],
        "edges": [
            {"from": "a", "to": "b"},   # b is a dangling target
            {"from": "c", "to": "a"},   # c is a dangling source
        ],
    }
    index = GraphIndex(data)
    # b is a target — appears in incoming, c is a source — appears in outgoing
    assert "b" in index.incoming
    assert "c" in index.outgoing
    assert index.get_node("b") is None
    assert index.get_node("c") is None
    # get_neighbors filters to nodes_by_id, so dangling nodes don't appear
    assert index.get_neighbors("a", direction="outgoing") == []
    assert index.get_neighbors("a", direction="incoming") == []


def test_multiple_edges_from_same_source():
    """Multiple edges from the same source are all collected."""
    data = {
        "nodes": [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
        ],
        "edges": [
            {"from": "a", "to": "b", "relation": "calls"},
            {"from": "a", "to": "c", "relation": "uses"},
        ],
    }
    index = GraphIndex(data)
    assert len(index.outgoing["a"]) == 2
    neighbors = index.get_neighbors("a", direction="outgoing")
    ids = {n["id"] for n in neighbors}
    assert ids == {"b", "c"}


def test_self_loop_edge():
    """A self-loop edge (from == to) appears in both outgoing and incoming."""
    data = {
        "nodes": [{"id": "a"}],
        "edges": [
            {"from": "a", "to": "a", "relation": "recursive"},
        ],
    }
    index = GraphIndex(data)
    assert len(index.outgoing["a"]) == 1
    assert len(index.incoming["a"]) == 1
    assert index.outgoing["a"][0]["to"] == "a"
    assert index.incoming["a"][0]["from"] == "a"
    neighbors_out = index.get_neighbors("a", direction="outgoing")
    neighbors_in = index.get_neighbors("a", direction="incoming")
    assert len(neighbors_out) == 1
    assert neighbors_out[0]["id"] == "a"
    assert len(neighbors_in) == 1
    assert neighbors_in[0]["id"] == "a"
