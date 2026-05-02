"""
tiered_builder.py — Transform flat CodeGraph into hierarchical tier graphs.

Takes a fully-built flat CodeGraph and produces:
1. Entry point detection (main.py, graph roots, __init__.py)
2. Sub-graphs for each entry point (with stubs for imported files)
3. Tier files: symbol, file, directory, repo (each with aggregated edges)
4. Table of contents (toc.json)

All output paths use forward slashes (normalized for JSON).
"""

from __future__ import annotations
import json
import math
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

from .schema import Node, Edge, NodeType, EdgeRelation
from .schema import file_id, symbol_id, dir_id, repo_id, is_test_file
from .graph import CodeGraph


# =============================================================================
# Entry Point Detection
# =============================================================================

def _detect_entry_points(graph: CodeGraph, feature: str) -> List[Dict[str, str]]:
    """
    Detect entry point files using tightened priority-ordered rules.

    A file is an entry point ONLY if it meets one of:
    1. Contains `if __name__ == "__main__"` block (scanned from disk) AND
       does not match script/migration/setup path or filename patterns.
    2. Is an __init__.py file (package surface).

    Test files (test_*.py, conftest.py) are NEVER entry points.

    Returns list of dicts: {"slug": str, "file": str, "reason": str}
    """
    # Path substrings that disqualify a __main__ file from being an entry point
    _SCRIPT_PATH_PATTERNS = {
        "/tests/",
        "/test_scripts/",
        "test_scripts/",   # top-level test_scripts/ directory
        "/scripts/",
        "/first_boot/",
        "/db/",
        "/utils/",         # utility modules with dev-only __main__ blocks
    }

    # Filename prefixes that disqualify a __main__ file from being an entry point
    _SCRIPT_FILENAME_PREFIXES = (
        "test_",
        "autocomplete_",
        "migrate_",
        "populate_",
        "rebuild_",
        "setup_",
        "create_",
        "analyze_",
        "repopulate_",
        "fix_",
        "sync_",
        "consolidate_",
        "derive_",
        "validate_",
        "batch_",
        "export_",
    )

    file_nodes = {n.id: n for n in graph.nodes if n.type == NodeType.FILE}
    if not file_nodes:
        return []

    def _has_main_block(file_path: str) -> bool:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                src = fh.read()
                return '__name__' in src and '__main__' in src
        except OSError:
            return False

    def _is_script_file(file_path: str, filename: str) -> bool:
        """Return True if the file matches script/migration/setup patterns."""
        normalized = file_path.replace("\\", "/")
        for pattern in _SCRIPT_PATH_PATTERNS:
            if pattern in normalized:
                return True
        if filename.startswith(_SCRIPT_FILENAME_PREFIXES):
            return True
        return False

    def _file_has_exports(file_id: str) -> bool:
        """Return True if the file node has at least one defines or contains edge."""
        for edge in graph.edges:
            if edge.from_id == file_id and edge.relation in (EdgeRelation.DEFINES, EdgeRelation.CONTAINS):
                return True
        return False

    # Collect files that contain symbols explicitly marked entry_point=True
    entry_point_files: dict[str, str] = {}  # file_path -> symbol label
    for n in graph.nodes:
        if n.type == NodeType.SYMBOL and getattr(n, "entry_point", False) and n.file:
            entry_point_files.setdefault(n.file, n.label)

    entry_points = []
    seen_files = set()

    for node_id, node in file_nodes.items():
        if not node.file:
            continue
        file_path = node.file
        filename = file_path.replace("\\", "/").split("/")[-1]

        # NEVER include test files
        if is_test_file(file_path):
            continue

        if file_path in seen_files:
            continue

        # Rule 1: if __name__ == "__main__" block present, but not a script file
        if _has_main_block(file_path) and not _is_script_file(file_path, filename):
            slug = _make_slug(file_path)
            entry_points.append({
                "slug": slug,
                "file": file_path,
                "reason": "contains if __name__ == '__main__' block",
            })
            seen_files.add(file_path)
            continue

        # Rule 2: file contains a symbol marked entry_point=True (route handlers, etc.)
        if file_path in entry_point_files:
            slug = _make_slug(file_path)
            entry_points.append({
                "slug": slug,
                "file": file_path,
                "reason": f"contains entry point: {entry_point_files[file_path]}",
            })
            seen_files.add(file_path)
            continue

        # Rule 3: __init__.py with meaningful content (has defines/contains edges)
        if filename == "__init__.py" and _file_has_exports(node_id):
            slug = _make_slug(file_path)
            entry_points.append({
                "slug": slug,
                "file": file_path,
                "reason": "package surface with exports (__init__.py)",
            })
            seen_files.add(file_path)
            continue

    # Rule 3: C++ main() functions
    symbol_nodes = {n.id: n for n in graph.nodes if n.type == NodeType.SYMBOL}
    for node_id, node in symbol_nodes.items():
        if node.label == "main" and node.file:
            file_path = node.file
            ext = file_path.rsplit('.', 1)[-1] if '.' in file_path else ''
            if ext in ('cc', 'cpp', 'c'):
                if file_path not in seen_files:
                    slug = _make_slug(file_path)
                    entry_points.append({
                        "slug": slug,
                        "file": file_path,
                        "reason": "C++ main() function",
                    })
                    seen_files.add(file_path)

    return entry_points


def _make_slug(file_path: str) -> str:
    """
    Create slug from file path:
    'Client_Side/utils/autofill_engine.py' -> 'main_Client_Side_utils_autofill_engine'
    """
    # Normalize to forward slashes
    file_path = file_path.replace("\\", "/")
    # Remove .py extension
    if file_path.endswith(".py"):
        file_path = file_path[:-3]
    # Replace / with _
    slug = file_path.replace("/", "_")
    return f"main_{slug}"


def _extract_file_from_id(node_id: str, feature: str) -> Optional[str]:
    """
    Extract file path from a node ID.
    Examples:
      "feature::Client_Side/main.py" -> "Client_Side/main.py"
      "feature::Client_Side/main.py::some_function" -> "Client_Side/main.py"
      "stdlib::json" -> None
    """
    if not node_id.startswith(f"{feature}::"):
        return None

    remainder = node_id[len(f"{feature}::"):]

    # Check for file path (contains .py)
    if ".py" in remainder:
        # Split by :: to separate file from symbol
        parts = remainder.split("::")
        file_part = parts[0]
        # Normalize to forward slashes for return
        return file_part.replace("\\", "/")

    return None


# =============================================================================
# Sub-graph Generation
# =============================================================================

def _build_sub_graph(
    graph: CodeGraph,
    entry_file: str,
    feature: str,
    all_entry_points: List[Dict[str, str]]
) -> Dict:
    """
    Build sub-graph JSON for one entry point file.

    Includes:
    - Entry point file node
    - All symbols/types in that file
    - Edges between those nodes
    - Stub file nodes for imported files (with ref if they're entry points)
    - Import edges to stubs

    Returns dict ready for JSON serialization.
    """
    sub_nodes = []
    sub_edges = []
    imported_files = set()

    # 1. Add entry point file node
    entry_node = None
    for n in graph.nodes:
        if n.type == NodeType.FILE and n.file == entry_file:
            entry_node = n
            sub_nodes.append(n.to_dict())
            break

    if not entry_node:
        # File node doesn't exist, create a stub
        entry_node = Node(
            id=file_id(feature, entry_file),
            type=NodeType.FILE,
            label=Path(entry_file).name,
            file=entry_file,
            line=None,
            language="python"
        )
        sub_nodes.append(entry_node.to_dict())

    # 2. Add all symbols/types defined in this file
    symbol_ids_in_file = set()
    for n in graph.nodes:
        if n.type in (NodeType.SYMBOL, NodeType.TYPE) and n.file == entry_file:
            sub_nodes.append(n.to_dict())
            symbol_ids_in_file.add(n.id)

    # 3. Add edges between nodes in this sub-graph
    for edge in graph.edges:
        if edge.from_id in symbol_ids_in_file or edge.from_id == entry_node.id:
            if edge.to_id in symbol_ids_in_file or edge.to_id == entry_node.id:
                # Internal edge
                sub_edges.append(edge.to_dict())
            else:
                # Outgoing edge: check if it's an import
                if edge.relation == EdgeRelation.IMPORTS:
                    to_file = _extract_file_from_id(edge.to_id, feature)
                    if to_file and to_file not in imported_files:
                        imported_files.add(to_file)

    # 4. Add import edges and stub file nodes for imported files
    for import_edge in graph.edges:
        if import_edge.relation == EdgeRelation.IMPORTS:
            if import_edge.from_id == entry_node.id:
                to_file = _extract_file_from_id(import_edge.to_id, feature)
                if to_file and to_file != entry_file:
                    imported_files.add(to_file)

                    # Check if this file is an entry point
                    ref = None
                    for ep in all_entry_points:
                        if ep["file"] == to_file:
                            ref = f"sub/{ep['slug']}.json"
                            break

                    if ref is None:
                        ref = "tier_file.json"

                    # Create stub node
                    stub_id = file_id(feature, to_file)
                    stub = Node(
                        id=stub_id,
                        type=NodeType.FILE,
                        label=Path(to_file).name,
                        file=to_file,
                        line=None,
                        language="python",
                        ref=ref
                    )
                    sub_nodes.append(stub.to_dict())

                    # Add import edge
                    sub_edges.append(import_edge.to_dict())

    # Inject spatial positions for sub-graph nodes
    # Entry file node at center (0, 0)
    entry_node_id = file_id(feature, entry_file)
    stub_nodes = []
    symbol_nodes_by_file: Dict[str, List[dict]] = defaultdict(list)

    for node_dict in sub_nodes:
        if node_dict["id"] == entry_node_id:
            node_dict["x"] = 0.0
            node_dict["y"] = 0.0
        elif node_dict.get("type") in ("symbol", "type"):
            symbol_nodes_by_file[node_dict.get("file", "")].append(node_dict)
        else:
            # stub file node
            stub_nodes.append(node_dict)

    # Symbols cluster around their file node (radius 60)
    # For symbols in the entry file, cluster around (0, 0)
    for file_path, syms in symbol_nodes_by_file.items():
        # Find file position (entry file is at 0,0; stubs haven't been positioned yet)
        if file_path == entry_file:
            fx, fy = 0.0, 0.0
        else:
            # Will be positioned after stubs are laid out; default to 0,0 for now
            fx, fy = 0.0, 0.0
        n_syms = len(syms)
        for i, node_dict in enumerate(syms):
            angle = i * 2 * math.pi / n_syms if n_syms > 1 else 0.0
            node_dict["x"] = fx + 60.0 * math.cos(angle)
            node_dict["y"] = fy + 60.0 * math.sin(angle)

    # Stub file nodes in a circle of radius 200 around (0, 0)
    n_stubs = len(stub_nodes)
    for i, node_dict in enumerate(stub_nodes):
        angle = i * 2 * math.pi / n_stubs if n_stubs > 1 else 0.0
        node_dict["x"] = 200.0 * math.cos(angle)
        node_dict["y"] = 200.0 * math.sin(angle)

    return {
        "feature": feature,
        "entry_point": entry_file,
        "stats": {
            "nodes": len(sub_nodes),
            "edges": len(sub_edges)
        },
        "nodes": sub_nodes,
        "edges": sub_edges
    }


# =============================================================================
# Spatial Positioning
# =============================================================================

def _compute_directory_positions(graph: CodeGraph) -> Dict[str, Tuple[float, float]]:
    """
    Compute deterministic grid positions for all directory nodes.
    Returns {dir_node_id: (x, y)}.
    """
    # Collect all unique directories from file nodes
    dir_paths = set()
    for n in graph.nodes:
        if n.type == NodeType.FILE and n.file:
            dir_path = str(Path(n.file).parent).replace("\\", "/")
            if dir_path == ".":
                dir_path = ""
            dir_paths.add(dir_path)

    # Sort: by depth then alphabetically
    def sort_key(p):
        return (p.count("/") if p else 0, p)
    sorted_dirs = sorted(dir_paths, key=sort_key)

    n = len(sorted_dirs)
    cols = max(1, int(math.sqrt(n)))
    positions = {}
    for idx, dir_path in enumerate(sorted_dirs):
        col = idx % cols
        row = idx // cols
        node_id = dir_id(graph.feature, dir_path if dir_path else ".")
        positions[node_id] = (col * 250.0, row * 200.0)
    return positions


# =============================================================================
# Tier File Generation
# =============================================================================

def _build_tier_symbol(graph: CodeGraph) -> Dict:
    """
    Tier symbol = the flat graph itself.
    Copy as tier_symbol.json.
    """
    return graph.to_dict()


def _build_tier_file(graph: CodeGraph) -> Dict:
    """
    Tier file: One node per file.
    Edges:
    - imports edges between files (as-is)
    - calls edges within different files -> depends_on (deduplicated, with count)
    """
    file_nodes = {}
    file_edges_map = defaultdict(int)  # (from_file, to_file) -> count
    import_edges = []

    # Collect file nodes
    for n in graph.nodes:
        if n.type == NodeType.FILE:
            file_nodes[n.id] = n

    # Process edges
    for edge in graph.edges:
        if edge.relation == EdgeRelation.IMPORTS:
            # Keep import edges as-is
            import_edges.append(edge)
        elif edge.relation == EdgeRelation.CALLS:
            # Convert calls between different files to depends_on
            from_file = _extract_file_from_id(edge.from_id, graph.feature)
            to_file = _extract_file_from_id(edge.to_id, graph.feature)

            if from_file and to_file and from_file != to_file:
                from_file_id = file_id(graph.feature, from_file)
                to_file_id = file_id(graph.feature, to_file)
                file_edges_map[(from_file_id, to_file_id)] += 1

    # Build output edges
    output_edges = []
    for edge in import_edges:
        output_edges.append(edge.to_dict())

    for (from_id, to_id), count in file_edges_map.items():
        edge_dict = {
            "from": from_id,
            "to": to_id,
            "relation": EdgeRelation.DEPENDS_ON.value,
            "count": count
        }
        output_edges.append(edge_dict)

    output_nodes = [n.to_dict() for n in file_nodes.values()]

    # Inject spatial positions — files cluster around their parent directory
    dir_positions = _compute_directory_positions(graph)
    # Group files by directory
    dir_file_groups: Dict[str, List[dict]] = defaultdict(list)
    for node_dict in output_nodes:
        file_path = node_dict.get("file") or ""
        dir_path = str(Path(file_path).parent).replace("\\", "/") if file_path else ""
        if dir_path == ".":
            dir_path = ""
        d_id = dir_id(graph.feature, dir_path if dir_path else ".")
        dir_file_groups[d_id].append(node_dict)

    for d_id, file_list in dir_file_groups.items():
        dir_x, dir_y = dir_positions.get(d_id, (0.0, 0.0))
        n_files = len(file_list)
        for i, node_dict in enumerate(file_list):
            angle = i * 2 * math.pi / n_files if n_files > 1 else 0.0
            node_dict["x"] = dir_x + 100.0 * math.cos(angle)
            node_dict["y"] = dir_y + 100.0 * math.sin(angle)

    return {
        "feature": graph.feature,
        "stats": {
            "nodes": len(output_nodes),
            "edges": len(output_edges)
        },
        "nodes": output_nodes,
        "edges": output_edges
    }


def _build_tier_directory(graph: CodeGraph) -> Dict:
    """
    Tier directory: One node per directory.
    Edges: depends_on between directories (deduplicated, with count from file-level edges).
    """
    tier_file = _build_tier_file(graph)

    # Map file -> directory
    file_to_dir = {}
    for node_dict in tier_file["nodes"]:
        if "file" in node_dict and node_dict["file"]:
            file_path = node_dict["file"]
            dir_path = str(Path(file_path).parent)
            if dir_path == ".":
                dir_path = ""
            file_to_dir[node_dict["id"]] = dir_path

    # Collect unique directories with file counts
    dir_counts = Counter()
    for file_id_key, dir_path in file_to_dir.items():
        dir_counts[dir_path] += 1

    # Build directory nodes
    dir_nodes = {}
    for dir_path in dir_counts:
        node_id = dir_id(graph.feature, dir_path) if dir_path else dir_id(graph.feature, ".")
        label = Path(dir_path).name if dir_path and dir_path != "." else "root"
        count = dir_counts[dir_path]
        dir_nodes[dir_path] = Node(
            id=node_id,
            type=NodeType.DIRECTORY,
            label=label,
            file=None,
            line=None,
            language="python",
            count=count
        )

    # Aggregate file edges to directory edges
    dir_edges_map = defaultdict(int)  # (from_dir, to_dir) -> count
    for edge_dict in tier_file["edges"]:
        from_id = edge_dict["from"]
        to_id = edge_dict["to"]

        from_dir = file_to_dir.get(from_id)
        to_dir = file_to_dir.get(to_id)

        if from_dir is not None and to_dir is not None and from_dir != to_dir:
            from_dir_id = dir_id(graph.feature, from_dir) if from_dir else dir_id(graph.feature, ".")
            to_dir_id = dir_id(graph.feature, to_dir) if to_dir else dir_id(graph.feature, ".")
            count = edge_dict.get("count", 1)
            dir_edges_map[(from_dir_id, to_dir_id)] += count

    # Build output edges
    output_edges = []
    for (from_dir_id, to_dir_id), count in dir_edges_map.items():
        edge_dict = {
            "from": from_dir_id,
            "to": to_dir_id,
            "relation": EdgeRelation.DEPENDS_ON.value,
            "count": count
        }
        output_edges.append(edge_dict)

    output_nodes = [n.to_dict() for n in dir_nodes.values()]

    # Inject spatial positions
    dir_positions = _compute_directory_positions(graph)
    for node_dict in output_nodes:
        pos = dir_positions.get(node_dict["id"], (0.0, 0.0))
        node_dict["x"] = pos[0]
        node_dict["y"] = pos[1]

    return {
        "feature": graph.feature,
        "stats": {
            "nodes": len(output_nodes),
            "edges": len(output_edges)
        },
        "nodes": output_nodes,
        "edges": output_edges
    }


def _build_tier_repo(graph: CodeGraph) -> Dict:
    """
    Tier repo: Single node for repo root.
    Edges: contains edges to all directory nodes.
    """
    tier_directory = _build_tier_directory(graph)

    # Create repo node
    repo_node = Node(
        id=repo_id(graph.feature, "repo"),
        type=NodeType.REPO,
        label="repo",
        file=None,
        line=None,
        language="python",
        count=sum(n.get("count", 0) for n in tier_directory["nodes"] if n.get("type") == NodeType.DIRECTORY.value)
    )

    # Create contains edges to all directories
    output_edges = []
    for dir_node_dict in tier_directory["nodes"]:
        edge_dict = {
            "from": repo_node.id,
            "to": dir_node_dict["id"],
            "relation": EdgeRelation.CONTAINS.value
        }
        output_edges.append(edge_dict)

    output_nodes = [repo_node.to_dict()]
    output_nodes.extend(tier_directory["nodes"])

    return {
        "feature": graph.feature,
        "stats": {
            "nodes": len(output_nodes),
            "edges": len(output_edges)
        },
        "nodes": output_nodes,
        "edges": output_edges
    }


# =============================================================================
# Table of Contents
# =============================================================================

def _build_toc(
    feature: str,
    entry_points: List[Dict[str, str]],
    all_file_slugs: Dict[str, str],  # file_path -> slug
) -> Dict:
    """
    Build toc.json with entry points, per-file sub-graph map, tier file references, and metadata.
    """
    toc_entry_points = []
    for ep in entry_points:
        toc_entry_points.append({
            "slug": ep["slug"],
            "file": ep["file"],
            "reason": ep["reason"],
            "graph": f"sub/{ep['slug']}.json"
        })

    # files: map of file_path -> {slug, graph} for ALL files with sub-graphs
    toc_files = {}
    for file_path, slug in all_file_slugs.items():
        toc_files[file_path] = {
            "slug": slug,
            "graph": f"sub/{slug}.json"
        }

    # dirs: sorted unique directory paths derived from all file paths
    dir_set: set[str] = set()
    for fp in toc_files:
        parts = fp.split("/")
        for i in range(1, len(parts)):
            dir_set.add("/".join(parts[:i]))
    toc_dirs = sorted(dir_set)

    return {
        "generated": datetime.utcnow().isoformat() + "Z",
        "feature": feature,
        "tiers": ["repo", "directory", "file", "symbol"],
        "entry_points": toc_entry_points,
        "files": toc_files,
        "dirs": toc_dirs,
        "tier_files": {
            "symbol": "tier_symbol.json",
            "file": "tier_file.json",
            "directory": "tier_directory.json",
            "repo": "tier_repo.json"
        }
    }


# =============================================================================
# Public API
# =============================================================================

def build_tiers(feature_graph: CodeGraph, graphs_dir: Path, feature: str) -> None:
    """
    Given a fully-built flat CodeGraph, emit all tier files and sub-graphs
    into graphs_dir. Creates graphs_dir/sub/ if needed.

    Outputs:
    - graphs/toc.json
    - graphs/tier_symbol.json
    - graphs/tier_file.json
    - graphs/tier_directory.json
    - graphs/tier_repo.json
    - graphs/sub/main_*.json (one per entry point)
    """
    graphs_dir.mkdir(parents=True, exist_ok=True)
    sub_dir = graphs_dir / "sub"
    sub_dir.mkdir(parents=True, exist_ok=True)

    # 1. Detect entry points
    entry_points = _detect_entry_points(feature_graph, feature)
    print(f"[tiered_builder] Entry points detected: {len(entry_points)}")
    for ep in entry_points:
        print(f"  - {ep['slug']}: {ep['file']} ({ep['reason']})")

    # 2. Generate tier files
    print("[tiered_builder] Generating tier files...")

    tier_symbol_data = _build_tier_symbol(feature_graph)
    tier_file_data = _build_tier_file(feature_graph)
    tier_directory_data = _build_tier_directory(feature_graph)
    tier_repo_data = _build_tier_repo(feature_graph)

    _save_json(graphs_dir / "tier_symbol.json", tier_symbol_data)
    _save_json(graphs_dir / "tier_file.json", tier_file_data)
    _save_json(graphs_dir / "tier_directory.json", tier_directory_data)
    _save_json(graphs_dir / "tier_repo.json", tier_repo_data)

    # 3. Generate sub-graphs for ALL files (entry points first, then remaining)
    ep_files = {ep["file"] for ep in entry_points}
    all_file_nodes = [
        n for n in feature_graph.nodes
        if hasattr(n, "type") and n.type.value == "file" and n.file
    ]
    all_file_slugs: Dict[str, str] = {}  # file_path -> slug

    # Entry point sub-graphs
    print(f"[tiered_builder] Generating {len(entry_points)} entry-point sub-graphs...")
    for ep in entry_points:
        sub_graph_data = _build_sub_graph(feature_graph, ep["file"], feature, entry_points)
        sub_file = sub_dir / f"{ep['slug']}.json"
        _save_json(sub_file, sub_graph_data)
        all_file_slugs[ep["file"]] = ep["slug"]

    # Per-file sub-graphs for remaining files
    non_ep_files = [n for n in all_file_nodes if n.file not in ep_files]
    print(f"[tiered_builder] Generating {len(non_ep_files)} per-file sub-graphs...")
    for file_node in non_ep_files:
        if not file_node.file:
            continue
        file_path = file_node.file.replace("\\", "/")
        slug = _make_slug(file_path)
        sub_graph_data = _build_sub_graph(feature_graph, file_path, feature, entry_points)
        sub_file = sub_dir / f"{slug}.json"
        _save_json(sub_file, sub_graph_data)
        all_file_slugs[file_path] = slug

    # 4. Generate toc.json
    toc_data = _build_toc(feature, entry_points, all_file_slugs)
    _save_json(graphs_dir / "toc.json", toc_data)

    print(f"[tiered_builder] Complete -> {graphs_dir / 'toc.json'}")


def _save_json(path: Path, data: Dict) -> None:
    """Save a dict to JSON file with normalized paths."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
