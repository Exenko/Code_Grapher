"""
run.py — CLI entry point for CodeGrapher.

Usage:
    py run.py --feature autofill --root /path/to/project --files "src/*.py" "tests/test_*.py"

Reusable on any Python project — no project-specific logic here.

Two-pass algorithm:
  Pass 1: Parse each file independently, collect all node IDs into a registry.
  Pass 2: Re-parse (or resolve in-place) to upgrade unresolved `calls` edges
          using the full cross-file symbol registry.

Output:
  - graphs/feature_<name>.json         (raw graph data)
  - viewer/index.html                  (updated with embedded GRAPH_DATA)
"""

from __future__ import annotations
import argparse
import glob as glob_module
import json
import sys
from pathlib import Path
from typing import Optional

# Ensure CodeGrapher directory is on path when run from project root
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

import ast as _ast_mod

from schema import NodeType
from graph import CodeGraph
from parser_python import parse_file as parse_python, resolve_calls, _annotation_names, _is_builtin_type
from parser_cpp import parse_file as parse_cpp
from parser_proto import parse_file as parse_proto
from parser_xml import parse_file as parse_xml
from tiered_builder import build_tiers


# ---------------------------------------------------------------------------
# File parsing dispatch
# ---------------------------------------------------------------------------

def _parse_one(feature: str, root: Path, filepath: Path,
               known_symbol_ids: set | None = None,
               known_return_types: dict | None = None) -> CodeGraph | None:
    """Dispatch to appropriate parser based on file suffix."""
    suffix = filepath.suffix.lower()
    if suffix == '.py':
        return parse_python(feature, root, filepath, known_symbol_ids, known_return_types)
    elif suffix in ('.cc', '.c', '.h', '.hpp', '.cpp'):
        return parse_cpp(feature, root, filepath, known_symbol_ids)
    elif suffix == '.proto':
        return parse_proto(feature, root, filepath, known_symbol_ids)
    elif suffix == '.xml':
        return parse_xml(feature, root, filepath, known_symbol_ids)
    else:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    root = Path(args.root).resolve()
    feature = args.feature
    cg_dir = _HERE  # CodeGrapher/ directory

    # Resolve files from --files and --dir, combining and deduplicating results
    all_files_set: set[Path] = set()
    if args.files:
        all_files_set.update(_resolve_globs(root, args.files))
    if args.dir:
        all_files_set.update(_resolve_dirs(root, args.dir))

    all_files = sorted(all_files_set)
    if not all_files:
        print(f"[ERROR] No files matched the given patterns in {root}")
        sys.exit(1)

    print(f"\nCodeGrapher — feature: {feature}")
    print(f"  root:  {root}")
    print(f"  files: {len(all_files)} matched\n")
    for f in sorted(all_files):
        rel = str(f.relative_to(root)).replace("\\", "/")
        print(f"    {rel}")
    print()

    # ------------------------------------------------------------------
    # Pass 1: Parse all files, collect symbol registry
    # ------------------------------------------------------------------
    print("Pass 1: Parsing files...")
    per_file_graphs: list[CodeGraph] = []
    for filepath in all_files:
        g = _parse_one(feature, root, filepath, known_symbol_ids=None)
        if g is not None:
            per_file_graphs.append(g)

    # Build cross-file symbol registry from Pass 1 results
    registry: set[str] = set()
    for g in per_file_graphs:
        registry.update(g.all_symbol_ids())

    print(f"  Registry: {len(registry)} symbols/types found\n")

    # Build cross-file return type map: function_label → return_type_class_name.
    # Scanned directly from Python source AST rather than from Pass 1 edges.
    # Edge-based extraction fails because in Pass 1 (empty known registry),
    # _emit_return_type_edge can't resolve cross-file type nodes and skips them.
    # Direct AST scan is registry-independent and always captures annotations.
    # Used in Pass 2 to resolve instance method calls like:
    #   db = get_database()   # get_database -> PostgresDatabaseUtility
    #   db.execute(query)     # resolved to PostgresDatabaseUtility.execute
    return_type_map: dict[str, str] = {}
    for filepath in all_files:
        if filepath.suffix.lower() != '.py':
            continue
        try:
            source = filepath.read_text(encoding='utf-8', errors='replace')
            tree = _ast_mod.parse(source, filename=str(filepath))
        except Exception:
            continue
        for node in _ast_mod.walk(tree):
            if isinstance(node, (_ast_mod.FunctionDef, _ast_mod.AsyncFunctionDef)):
                if node.returns:
                    for tname in _annotation_names(node.returns):
                        if not _is_builtin_type(tname):
                            return_type_map[node.name] = tname
                            break

    print(f"  Return type map: {len(return_type_map)} annotated functions\n")

    # ------------------------------------------------------------------
    # Pass 2: Re-parse with full registry to resolve calls
    # ------------------------------------------------------------------
    print("Pass 2: Resolving cross-file calls...")
    feature_graph = CodeGraph(feature)
    for filepath in all_files:
        g = _parse_one(feature, root, filepath,
                       known_symbol_ids=registry,
                       known_return_types=return_type_map)
        if g is not None:
            feature_graph.merge(g)

    print(f"  Nodes: {feature_graph.node_count()}")
    print(f"  Edges: {feature_graph.edge_count()}\n")

    # Collapse forward-declared duplicates to a single canonical type node
    feature_graph.dedup_type_nodes_by_label()

    # ------------------------------------------------------------------
    # Write graph JSON
    # ------------------------------------------------------------------
    graphs_dir = cg_dir / "graphs"
    out_path = graphs_dir / f"feature_{feature}.json"
    feature_graph.save(out_path)
    print(f"Graph written -> {out_path}")

    # ------------------------------------------------------------------
    # Build tiered graphs (sub-graphs, tier files, toc.json)
    # ------------------------------------------------------------------
    print("\nBuilding tiered graphs...")
    build_tiers(feature_graph, graphs_dir, feature)

    # ------------------------------------------------------------------
    # Annotate graph with cross_file and entry_distance
    # ------------------------------------------------------------------
    print("\nAnnotating graph...")
    _annotate_graph(graphs_dir)

    # ------------------------------------------------------------------
    # Run analyzer if requested
    # ------------------------------------------------------------------
    if args.analyze == "flow":
        _run_flow_analysis(graphs_dir, args.entry, feature)
    elif args.analyze == "type":
        _run_type_analysis(graphs_dir, args.type_name)

    # ------------------------------------------------------------------
    # Standalone viewer HTML vs. LOD server mode
    # ------------------------------------------------------------------
    standalone = args.standalone
    if standalone is None:
        standalone = feature_graph.node_count() < 1000

    viewer_template = cg_dir / "viewer" / "index.html"
    if standalone:
        viewer_out = graphs_dir / f"viewer_{feature}.html"
        if viewer_template.exists():
            _build_standalone_viewer(feature_graph, viewer_template, cg_dir / "viewer", viewer_out)
            print(f"Viewer  -> {viewer_out}")
        else:
            print(f"[WARN] viewer/index.html not found -- skipping viewer")
    else:
        print(f"Run:  py CodeGrapher/serve.py --graphs {graphs_dir}")
        print(f"Then: http://localhost:5000")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    _print_summary(feature_graph)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CodeGrapher — Python codebase cartography tool"
    )
    p.add_argument("--feature", required=True,
                   help="Feature name (used in node IDs and output filename)")
    p.add_argument("--root", required=True,
                   help="Project root directory (all file paths are relative to this)")
    p.add_argument("--files", required=False, nargs="+",
                   help="File glob patterns relative to --root (e.g. 'src/*.py' 'tests/test_*.py')")
    p.add_argument("--dir", required=False, nargs="+", dest="dir",
                   help="Directory paths relative to --root (recursively finds all .py files)")
    p.add_argument("--standalone", action="store_true", default=None,
                   help="Bake graph into a self-contained HTML file (auto: on if <1000 nodes)")
    p.add_argument("--analyze", choices=["flow", "type"], default=None,
                   help="Run analyzer after building graph. 'flow' emits Mermaid flow diagram; 'type' expands a type/class tree")
    p.add_argument("--entry", default=None,
                   help="Entry file for --analyze flow (e.g. Client_Side/main.py). If omitted, uses first detected entry point from toc.json")
    p.add_argument("--type", default=None, dest="type_name",
                   help="Type/class name for --analyze type (e.g. CookingSession)")
    args = p.parse_args()
    if not args.files and not args.dir:
        p.error("At least one of --files or --dir must be provided")
    return args


def _resolve_globs(root: Path, patterns: list[str]) -> list[Path]:
    """Expand glob patterns relative to root, return sorted unique Paths."""
    matched: set[Path] = set()
    supported_suffixes = {'.py', '.cc', '.c', '.h', '.hpp', '.cpp', '.proto', '.xml'}
    for pattern in patterns:
        # Use glob_module with the full path
        full_pattern = str(root / pattern)
        hits = glob_module.glob(full_pattern, recursive=True)
        for h in hits:
            p = Path(h).resolve()
            if p.suffix.lower() in supported_suffixes and p.is_file():
                matched.add(p)
    return sorted(matched)


def _resolve_dirs(root: Path, dirs: list[str]) -> list[Path]:
    """Recursively find all supported source files in given directories relative to root, return sorted unique Paths."""
    matched: set[Path] = set()
    patterns = ["*.py", "*.cc", "*.c", "*.h", "*.hpp", "*.cpp", "*.proto", "*.xml"]
    for dir_path in dirs:
        full_dir = root / dir_path
        if full_dir.is_dir():
            for pattern in patterns:
                for src_file in full_dir.rglob(pattern):
                    p = src_file.resolve()
                    if p.is_file():
                        matched.add(p)
    return sorted(matched)


def _build_standalone_viewer(graph: CodeGraph, template: Path, viewer_dir: Path, out_path: Path) -> None:
    """
    Build a fully self-contained HTML file with D3, graph.js, styles.css,
    and GRAPH_DATA all inlined. Opens in any browser from file:// with no server.
    """
    content = template.read_text(encoding="utf-8")

    # 1. Inline GRAPH_DATA (replace sentinel block)
    graph_json = json.dumps(graph.to_dict())
    data_block = (
        "<!-- GRAPH_DATA:START -->\n"
        "<script>\n"
        f"const GRAPH_DATA = {graph_json};\n"
        "</script>\n"
        "<!-- GRAPH_DATA:END -->"
    )
    start = "<!-- GRAPH_DATA:START -->"
    end = "<!-- GRAPH_DATA:END -->"
    if start in content and end in content:
        si = content.index(start)
        ei = content.index(end) + len(end)
        content = content[:si] + data_block + content[ei:]

    # 2. Inline styles.css
    css_path = viewer_dir / "styles.css"
    if css_path.exists():
        css = css_path.read_text(encoding="utf-8")
        content = content.replace(
            '<link rel="stylesheet" href="styles.css">',
            f"<style>\n{css}\n</style>"
        )

    # 3. Inline d3.min.js
    d3_path = viewer_dir / "d3.min.js"
    if d3_path.exists():
        d3_src = d3_path.read_text(encoding="utf-8")
        content = content.replace(
            '<script src="d3.min.js"></script>',
            f"<script>\n{d3_src}\n</script>"
        )

    # 4. Inline graph.js
    js_path = viewer_dir / "graph.js"
    if js_path.exists():
        js_src = js_path.read_text(encoding="utf-8")
        content = content.replace(
            '<script src="graph.js"></script>',
            f"<script>\n{js_src}\n</script>"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")


def _run_flow_analysis(graphs_dir: Path, entry_file: Optional[str], feature: str) -> None:
    """Run flow trace analysis and print Mermaid output."""
    import sys
    _HERE_analyze = Path(__file__).parent / "analyze"
    sys.path.insert(0, str(_HERE_analyze.parent))

    try:
        from analyze.flow_trace import trace
    except ImportError as e:
        print(f"[WARN] Could not import analyze.flow_trace: {e}")
        return

    graph_path = str(graphs_dir / "tier_symbol.json")

    # If no entry file specified, pick first entry point from toc.json
    if not entry_file:
        toc_path = graphs_dir / "toc.json"
        if toc_path.exists():
            import json as _json
            toc = _json.loads(toc_path.read_text(encoding="utf-8"))
            eps = toc.get("entry_points", [])
            if eps:
                entry_file = eps[0]["file"]
                print(f"[analyze] No --entry specified, using first entry point: {entry_file}")

    if not entry_file:
        print("[analyze] No entry point found. Use --entry to specify one.")
        return

    print(f"\n[analyze] Tracing flow from: {entry_file}")
    result = trace(graph_path, entry_file)

    # Write to graphs dir as .mmd file
    safe_name = entry_file.replace("/", "_").replace("\\", "_").replace(".py", "")
    out_path = graphs_dir / f"flow_{safe_name}.mmd"
    out_path.write_text(result, encoding="utf-8")
    print(f"[analyze] Flow diagram -> {out_path}")
    print("\n" + result)


def _run_type_analysis(graphs_dir: Path, type_name: Optional[str]) -> None:
    """Run type expansion analysis and emit Mermaid classDiagram output."""
    _HERE_analyze = Path(__file__).parent / "analyze"
    sys.path.insert(0, str(_HERE_analyze.parent))

    try:
        from analyze.type_expander import expand, list_types
    except ImportError as e:
        print(f"[WARN] Could not import analyze.type_expander: {e}")
        return

    graph_path = str(graphs_dir / "tier_symbol.json")

    if not type_name:
        types = list_types(graph_path)
        print(f"[analyze] --type not specified. Available types ({len(types)}):")
        for t in types:
            print(f"  {t}")
        return

    print(f"\n[analyze] Expanding type: {type_name}")
    result = expand(graph_path, type_name, output="mermaid")

    safe_name = type_name.replace(".", "_")
    out_path = graphs_dir / f"type_{safe_name}.mmd"
    out_path.write_text(result, encoding="utf-8")
    print(f"[analyze] Type diagram -> {out_path}")
    print("\n" + result)


def _print_summary(graph: CodeGraph) -> None:
    from collections import Counter
    node_types = Counter(n.type.value for n in graph.nodes)
    edge_types = Counter(e.relation.value for e in graph.edges)
    unresolved = sum(1 for e in graph.edges if e.unresolved)

    print("\n--- Summary ---")
    print("Nodes by type:")
    for t, c in sorted(node_types.items()):
        print(f"  {t:12s}  {c}")
    print("Edges by relation:")
    for r, c in sorted(edge_types.items()):
        print(f"  {r:12s}  {c}")
    if unresolved:
        print(f"\n  ({unresolved} unresolved call edges — targets outside feature scope)")
    print()


def _annotate_graph(graphs_dir: Path) -> None:
    """
    Post-processing pass: annotate tier_symbol.json with two new fields.

    Per edge:
      cross_file (bool) — True if from_node.file != to_node.file.
                          Signals inter-file boundary crossings.

    Per node:
      entry_distance (int) — minimum hop count from any entry point via
                             outgoing 'calls' edges. 0 = entry point symbol,
                             None = unreachable from any entry point.

    Rewrites tier_symbol.json in-place. Safe to call multiple times
    (overwrites previous annotation).
    """
    import json as _json

    symbol_path = graphs_dir / "tier_symbol.json"
    toc_path = graphs_dir / "toc.json"

    if not symbol_path.exists() or not toc_path.exists():
        print("[annotate] tier_symbol.json or toc.json not found — skipping annotation")
        return

    with open(symbol_path, "r", encoding="utf-8") as f:
        data = _json.load(f)
    with open(toc_path, "r", encoding="utf-8") as f:
        toc = _json.load(f)

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    # Build file lookup: node_id -> file path
    node_file: dict[str, str] = {}
    for node in nodes:
        nid = node.get("id", "")
        file_path = node.get("file") or ""
        node_file[nid] = file_path

    # --- cross_file annotation on edges ---
    for edge in edges:
        from_file = node_file.get(edge.get("from", ""), "")
        to_file = node_file.get(edge.get("to", ""), "")
        # cross_file = True when both files are known and they differ
        if from_file and to_file:
            edge["cross_file"] = from_file != to_file
        else:
            edge["cross_file"] = False

    # --- entry_distance annotation on nodes ---
    # Step 1: find entry point symbol IDs from toc entry_points
    # An entry point file's symbols have entry_distance = 0 if they're
    # directly in the entry point file; the file node itself = 0.
    entry_files: set[str] = set()
    for ep in toc.get("entry_points", []):
        ep_file = ep.get("file", "").replace("\\", "/")
        if ep_file:
            entry_files.add(ep_file)

    # Seed: all nodes whose file is an entry point file get distance 0
    node_ids_by_file: dict[str, list[str]] = {}
    for node in nodes:
        f = (node.get("file") or "").replace("\\", "/")
        node_ids_by_file.setdefault(f, []).append(node["id"])

    entry_distance: dict[str, int] = {}
    seed_ids: list[str] = []
    for ep_file in entry_files:
        for nid in node_ids_by_file.get(ep_file, []):
            entry_distance[nid] = 0
            seed_ids.append(nid)

    # Step 2: BFS outward over 'calls' edges
    from collections import deque
    outgoing_calls: dict[str, list[str]] = {}
    for edge in edges:
        if edge.get("relation") == "calls":
            src = edge.get("from", "")
            dst = edge.get("to", "")
            if src and dst:
                outgoing_calls.setdefault(src, []).append(dst)

    queue: deque[str] = deque(seed_ids)
    while queue:
        nid = queue.popleft()
        current_dist = entry_distance[nid]
        for neighbor in outgoing_calls.get(nid, []):
            if neighbor not in entry_distance:
                entry_distance[neighbor] = current_dist + 1
                queue.append(neighbor)

    # Step 3: Write entry_distance back to nodes (None if unreachable)
    for node in nodes:
        node["entry_distance"] = entry_distance.get(node["id"])

    # Write back
    with open(symbol_path, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2)

    reachable = sum(1 for v in entry_distance.values() if v is not None)
    cross_file_count = sum(1 for e in edges if e.get("cross_file"))
    print(f"[annotate] entry_distance: {reachable}/{len(nodes)} nodes reachable from entry points")
    print(f"[annotate] cross_file: {cross_file_count}/{len(edges)} cross-file edges")


if __name__ == "__main__":
    main()
