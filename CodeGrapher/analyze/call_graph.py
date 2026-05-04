"""call_graph.py — Generate Mermaid diagrams from CodeGrapher graph JSON."""

import json
from collections import defaultdict, deque
from pathlib import Path


def _make_node_id_gen():
    """Return callable mapping node ids to short stable N0, N1, ... IDs."""
    cache = {}
    def get_id(nid: str) -> str:
        if nid not in cache:
            cache[nid] = f"N{len(cache)}"
        return cache[nid]
    return get_id


def _load_graph(graph_path: str) -> dict:
    """Load JSON graph; return {nodes_by_id, edges_by_from, all_nodes, all_edges}."""
    with open(graph_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes_by_id = {}
    for node in data.get("nodes", []):
        nodes_by_id[node["id"]] = node

    edges_by_from = defaultdict(list)
    for edge in data.get("edges", []):
        src = edge.get("from")
        if src:
            edges_by_from[src].append(edge)

    return {
        "nodes_by_id": nodes_by_id,
        "edges_by_from": edges_by_from,
        "all_edges": data.get("edges", []),
    }


def _truncate_label(label: str, max_len: int = 30) -> str:
    """Truncate label to max_len chars."""
    if len(label) > max_len:
        return label[:max_len-1] + "…"
    return label


def _is_back_edge(visited: set, target_id: str) -> bool:
    """Return True if target_id already visited (cycle/back-edge)."""
    return target_id in visited


def _should_skip(node_id: str) -> bool:
    """Skip unresolved and stdlib nodes."""
    return node_id.startswith("unresolved::") or node_id.startswith("stdlib::")


def flowchart(graph_path: str, node_id: str) -> str:
    """
    BFS from node_id over all outgoing edges. Max depth 6.
    Return flowchart TD Mermaid string.
    """
    graph = _load_graph(graph_path)
    nodes_by_id = graph["nodes_by_id"]
    edges_by_from = graph["edges_by_from"]

    if node_id not in nodes_by_id:
        raise ValueError(f"Node not found: {node_id}")

    node_id_gen = _make_node_id_gen()
    visited = set()
    mermaid_edges = []
    back_edges = set()

    # BFS
    queue = deque([(node_id, 0)])  # (node_id, depth)
    visited.add(node_id)
    seed_mid = node_id_gen(node_id)

    while queue:
        current_id, depth = queue.popleft()
        if depth > 6:
            continue

        current_node = nodes_by_id.get(current_id, {})
        current_mid = node_id_gen(current_id)

        # Walk outgoing edges
        for edge in edges_by_from.get(current_id, []):
            target_id = edge.get("to")
            if not target_id or _should_skip(target_id):
                continue

            if target_id not in nodes_by_id:
                continue

            target_node = nodes_by_id[target_id]
            target_mid = node_id_gen(target_id)
            relation = edge.get("relation", "")

            is_back = _is_back_edge(visited, target_id)
            if is_back:
                # Back-edge: use dotted arrow with cycle marker
                mermaid_edges.append(f"{current_mid} -.->|{relation} back| {target_mid}")
                back_edges.add((current_mid, target_mid))
            else:
                # Normal edge
                mermaid_edges.append(f"{current_mid} -->|{relation}| {target_mid}")
                visited.add(target_id)
                queue.append((target_id, depth + 1))

    # Build node declarations (visit order = BFS order via node_id_gen)
    # Collect all visited nodes
    node_decls = []
    for nid in visited:
        node = nodes_by_id.get(nid, {})
        label = _truncate_label(node.get("label", nid))
        file_basename = Path(node.get("file", "")).name if node.get("file") else ""
        mid = node_id_gen(nid)

        file_str = f"\n({file_basename})" if file_basename else ""
        node_decls.append(f'{mid}["{label}{file_str}"]')

    # Build mermaid
    lines = [
        "flowchart TD",
        "    " + "\n    ".join(node_decls),
        "    " + "\n    ".join(mermaid_edges),
        f"    class {seed_mid} seed",
        "    classDef seed fill:#0a1428,stroke:#2060a0,color:#4a8fd0",
    ]

    return "\n".join(lines)


def dataflow(graph_path: str, node_id: str) -> str:
    """
    BFS from node_id over DATA_FLOW_RELS = {produces, consumes, calls, defines}.
    Max depth 4. For type nodes, also walk inbound produces/consumes/uses_type.
    Return flowchart LR Mermaid string.
    """
    DATA_FLOW_RELS = {"produces", "consumes", "calls", "defines"}
    INBOUND_RELS = {"produces", "consumes", "uses_type"}

    graph = _load_graph(graph_path)
    nodes_by_id = graph["nodes_by_id"]
    edges_by_from = graph["edges_by_from"]
    all_edges = graph["all_edges"]

    if node_id not in nodes_by_id:
        raise ValueError(f"Node not found: {node_id}")

    node_id_gen = _make_node_id_gen()
    visited_nodes = set()      # plain node id strings
    visited_dirs = set()       # (node_id, direction) tuples
    mermaid_edges = []

    # Build reverse edge index for inbound lookups
    edges_by_to = defaultdict(list)
    for edge in all_edges:
        to_id = edge.get("to")
        if to_id:
            edges_by_to[to_id].append(edge)

    def _sort_neighbors(edges: list) -> list:
        """Sort edges by seq value (None->0)."""
        def get_seq(e):
            seq = e.get("seq")
            return seq if seq is not None else 0
        return sorted(edges, key=get_seq)

    # BFS outbound + inbound for type nodes
    queue = deque([(node_id, 0, "outbound")])  # (node_id, depth, direction)
    visited_nodes.add(node_id)
    visited_dirs.add((node_id, "outbound"))
    seed_mid = node_id_gen(node_id)

    while queue:
        current_id, depth, direction = queue.popleft()

        if depth > 4:
            continue

        current_node = nodes_by_id.get(current_id, {})
        current_mid = node_id_gen(current_id)

        if direction == "outbound":
            # Walk outbound edges
            edges = edges_by_from.get(current_id, [])
            edges = [e for e in edges if e.get("relation") in DATA_FLOW_RELS]
            edges = _sort_neighbors(edges)

            for edge in edges:
                target_id = edge.get("to")
                if not target_id or _should_skip(target_id):
                    continue
                if target_id not in nodes_by_id:
                    continue

                target_node = nodes_by_id[target_id]
                target_mid = node_id_gen(target_id)
                relation = edge.get("relation", "")
                seq = edge.get("seq")

                label = relation if seq is None else f"{relation} seq:{seq}"

                if target_id in visited_nodes:
                    mermaid_edges.append(f"{current_mid} -.->|{relation} back| {target_mid}")
                else:
                    mermaid_edges.append(f"{current_mid} -->|{label}| {target_mid}")
                    visited_nodes.add(target_id)
                    queue.append((target_id, depth + 1, "outbound"))

            # If type node, also explore inbound
            if current_node.get("type") == "type":
                if (current_id, "inbound") not in visited_dirs:
                    visited_dirs.add((current_id, "inbound"))
                    queue.append((current_id, 0, "inbound"))

        else:  # inbound
            # Walk inbound edges for type nodes
            edges = edges_by_to.get(current_id, [])
            edges = [e for e in edges if e.get("relation") in INBOUND_RELS]
            edges = _sort_neighbors(edges)

            for edge in edges:
                src_id = edge.get("from")
                if not src_id or _should_skip(src_id):
                    continue
                if src_id not in nodes_by_id:
                    continue

                src_node = nodes_by_id[src_id]
                src_mid = node_id_gen(src_id)
                relation = edge.get("relation", "")
                seq = edge.get("seq")

                label = relation if seq is None else f"{relation} seq:{seq}"

                if src_id in visited_nodes:
                    mermaid_edges.append(f"{src_mid} -.->|{relation} back| {current_mid}")
                else:
                    mermaid_edges.append(f"{src_mid} -->|{label}| {current_mid}")
                    visited_nodes.add(src_id)
                    # Inbound depth starts fresh at 1
                    if depth < 2:
                        queue.append((src_id, depth + 1, "inbound"))

    # Build node declarations
    node_decls = []
    for nid in visited_nodes:
        node = nodes_by_id.get(nid, {})
        label = _truncate_label(node.get("label", nid))
        file_basename = Path(node.get("file", "")).name if node.get("file") else ""
        mid = node_id_gen(nid)

        file_str = f"\n({file_basename})" if file_basename else ""
        node_decls.append(f'{mid}["{label}{file_str}"]')

    # Build mermaid
    lines = [
        "flowchart LR",
        "    " + "\n    ".join(node_decls),
        "    " + "\n    ".join(mermaid_edges),
        f"    class {seed_mid} seed",
        "    classDef seed fill:#0a1428,stroke:#2060a0,color:#4a8fd0",
    ]

    return "\n".join(lines)
