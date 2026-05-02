from __future__ import annotations


class GraphIndex:
    """Adjacency index over a loaded tier JSON dict (nodes + edges)."""

    def __init__(self, data: dict) -> None:
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        self.nodes_by_id: dict[str, dict] = {n["id"]: n for n in nodes}
        self.outgoing: dict[str, list[dict]] = {n["id"]: [] for n in nodes}
        self.incoming: dict[str, list[dict]] = {n["id"]: [] for n in nodes}

        for edge in edges:
            f, t = edge.get("from"), edge.get("to")
            if f and t:
                self.outgoing.setdefault(f, []).append(edge)
                self.incoming.setdefault(t, []).append(edge)

    def get_node(self, node_id: str) -> dict | None:
        return self.nodes_by_id.get(node_id)

    def get_neighbors(self, node_id: str, direction: str = "both") -> list[dict]:
        """Return neighbor node dicts. direction: 'outgoing', 'incoming', or 'both'."""
        neighbor_ids: set[str] = set()
        if direction in ("outgoing", "both"):
            for edge in self.outgoing.get(node_id, []):
                t = edge.get("to")
                if t:
                    neighbor_ids.add(t)
        if direction in ("incoming", "both"):
            for edge in self.incoming.get(node_id, []):
                f = edge.get("from")
                if f:
                    neighbor_ids.add(f)
        return [self.nodes_by_id[nid] for nid in neighbor_ids if nid in self.nodes_by_id]
