"""
graph.py — Core graph object: dedup, merge, serialize.

Reusable across any project. No project-specific logic here.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List
from .schema import Node, Edge, NodeType, EdgeRelation


# ------------------------------------------------------------------
# Free functions for mutation operations
# ------------------------------------------------------------------

def dedup_type_nodes_by_label(graph: CodeGraph) -> None:
    """Merge duplicate TYPE nodes that share the same label AND appear to be
    forward declarations (no outgoing 'contains' edges).

    When the same type is forward-declared in multiple files (e.g. EventBus
    in relay.h, output.h, and types.h), the parsers create separate type nodes
    with different IDs but the same label.  This function collapses them to a
    single canonical node — keeping the first-seen node ID — and rewrites all
    edge references to point to the canonical ID.

    Types with outgoing 'contains' edges are considered full definitions and
    are NOT merged, even if another node shares their label.

    General-purpose: safe to call after any multi-file parse.
    """
    from collections import defaultdict

    # Find which type nodes have outgoing 'contains' edges (full definitions)
    has_contains: set = set()
    for edge in graph._edges.values():
        if edge.relation.value == "contains":
            has_contains.add(edge.from_id)

    # Group TYPE nodes by label — only candidates with no contains edges
    by_label: dict = defaultdict(list)
    for node in graph._nodes.values():
        if node.type.value == "type":
            by_label[node.label].append(node.id)

    # For each label with duplicates, check if any candidate lacks contains edges
    # Only merge if AT LEAST ONE instance has no contains edges (forward decl)
    # Keep the node that HAS contains edges as canonical (if one exists)
    remap: dict = {}  # old_id -> canonical_id
    for label, ids in by_label.items():
        if len(ids) <= 1:
            continue

        full_defs = [nid for nid in ids if nid in has_contains]
        forward_decls = [nid for nid in ids if nid not in has_contains]

        if not forward_decls:
            # All instances are full definitions — don't merge (truly distinct types)
            continue

        # Pick canonical: prefer a full definition if one exists, else first forward decl
        canonical = full_defs[0] if full_defs else forward_decls[0]
        # Only remap forward declarations — full defs in other modules stay distinct
        for nid in forward_decls:
            if nid != canonical:
                remap[nid] = canonical

    if not remap:
        return

    # Remove remapped nodes
    for dup_id in remap:
        if dup_id in graph._nodes:
            del graph._nodes[dup_id]

    # Rewrite edges
    new_edges: dict = {}
    for key, edge in graph._edges.items():
        new_from = remap.get(edge.from_id, edge.from_id)
        new_to = remap.get(edge.to_id, edge.to_id)
        if new_from == new_to:
            continue  # drop self-loops created by dedup
        if new_from != edge.from_id or new_to != edge.to_id:
            from dataclasses import replace
            new_edge = replace(edge, from_id=new_from, to_id=new_to)
            new_key = new_edge.key()
            new_edges[new_key] = new_edge
        else:
            new_edges[key] = edge
    graph._edges = new_edges


def drop_ghost_nodes(graph: CodeGraph) -> int:
    """Remove unresolved phantom edge endpoints and any edges that reference them.

    Parsers emit edges to synthetic IDs when a call or type target cannot be
    resolved at parse time.  Two patterns exist:

      unresolved::<name>          — C++, Python, TS, Proto
      <feature>::<path>::_unresolved_.<name>  — Java, Kotlin

    These IDs never get add_node() calls, so they only appear as edge endpoints
    (not in _nodes).  Edges referencing them pollute the viewer and MCP since
    the tier builder indexes all edge endpoints regardless of node existence.

    Returns the number of ghost edge endpoints removed (distinct IDs).
    """
    def _is_ghost(node_id: str) -> bool:
        if node_id.startswith("unresolved::"):
            return True
        # Java/Kotlin pattern: feature::path/file.java::_unresolved_.methodName
        last = node_id.split("::")[-1]
        if last.startswith("_unresolved_."):
            return True
        return False

    # Collect ghost IDs from both node registry and edge endpoints
    ghost_ids: set[str] = {nid for nid in graph._nodes if _is_ghost(nid)}
    for edge in graph._edges.values():
        if _is_ghost(edge.from_id):
            ghost_ids.add(edge.from_id)
        if _is_ghost(edge.to_id):
            ghost_ids.add(edge.to_id)

    if not ghost_ids:
        return 0

    # Remove ghost nodes (if any were somehow registered)
    for gid in list(ghost_ids):
        graph._nodes.pop(gid, None)

    # Remove any edge that references a ghost endpoint
    graph._edges = {
        key: edge for key, edge in graph._edges.items()
        if edge.from_id not in ghost_ids and edge.to_id not in ghost_ids
    }

    return len(ghost_ids)


class CodeGraph:
    def __init__(self, feature: str):
        self.feature = feature
        self._nodes: Dict[str, Node] = {}   # id → Node
        self._edges: Dict[tuple, Edge] = {}  # (from, to, relation) → Edge

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Add a node. Silently deduplicates by id."""
        if node.id not in self._nodes:
            self._nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Add an edge. Deduplicates by (from, to, relation).
        If a resolved version already exists, don't overwrite with unresolved."""
        key = edge.key()
        existing = self._edges.get(key)
        if existing is None:
            self._edges[key] = edge
        elif existing.unresolved and not edge.unresolved:
            # Upgrade unresolved → resolved
            self._edges[key] = edge

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @property
    def nodes(self) -> List[Node]:
        return list(self._nodes.values())

    @property
    def edges(self) -> List[Edge]:
        return list(self._edges.values())

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return len(self._edges)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def all_symbol_ids(self) -> set:
        """Return all symbol and type node IDs — used for call resolution."""
        return {
            nid for nid, node in self._nodes.items()
            if node.type in (NodeType.SYMBOL, NodeType.TYPE)
        }

    def resolve_calls(self, known_symbol_ids: set) -> None:
        """Upgrade unresolved CALLS edges where target is now in registry."""
        for edge in self._edges.values():
            if edge.relation == EdgeRelation.CALLS and edge.unresolved:
                if edge.to_id in known_symbol_ids:
                    edge.unresolved = False

    # ------------------------------------------------------------------
    # Merge (Phase 2 use: stitch multiple feature graphs)
    # ------------------------------------------------------------------

    def merge(self, other: CodeGraph) -> None:
        """Merge another graph into this one in-place."""
        for node in other.nodes:
            self.add_node(node)
        for edge in other.edges:
            self.add_edge(edge)

    def dedup_type_nodes_by_label(self) -> None:
        """Merge duplicate TYPE nodes by label (wrapper for module-level function)."""
        dedup_type_nodes_by_label(self)

    def drop_ghost_nodes(self) -> int:
        """Remove ghost nodes (wrapper for module-level function)."""
        return drop_ghost_nodes(self)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "stats": {
                "nodes": self.node_count(),
                "edges": self.edge_count(),
            },
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> CodeGraph:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        g = cls(data["feature"])
        for n in data["nodes"]:
            g.add_node(Node(
                id=n["id"],
                type=NodeType(n["type"]),
                label=n["label"],
                file=n.get("file"),
                line=n.get("line"),
                language=n.get("language", "python"),
                is_dataclass=n.get("is_dataclass", False),
                is_test=n.get("is_test", False),
            ))
        for e in data["edges"]:
            g.add_edge(Edge(
                from_id=e["from"],
                to_id=e["to"],
                relation=EdgeRelation(e["relation"]),
                unresolved=e.get("unresolved", False),
            ))
        return g
