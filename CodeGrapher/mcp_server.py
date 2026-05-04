"""
CodeGrapher MCP Server

Provides LLM-accessible tools for navigating pre-built graph JSON files without re-parsing.
Implements lazy loading with LRU cache, node expansion, type tracing, and data flow analysis.

Graph layout expected under --graphs root:
    <graphs_root>/
        <project>/
            <graph-name>/
                toc.json
                tier_*.json
                sub/*.json

Graph selection (two modes, composable):
  - Active graph: call set_active_graph(project, graph) once; all subsequent tool calls
    use it automatically. Good for focused exploration of one graph.
  - Per-call override: pass graph="project/graph-name" on any individual tool call to
    target that graph for that call only, without changing the active graph. Good for
    spot comparisons or when orchestrating across multiple graphs.

If neither is set, tools return a helpful error with instructions.
"""

import argparse
import json
import sys
from collections import OrderedDict, deque
from dataclasses import dataclass
from heapq import heappush, heappop
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .graph_index import GraphIndex


# ============================================================================
# LRU Cache Implementation
# ============================================================================

class LRUCache:
    """OrderedDict-based LRU cache for tier data."""

    def __init__(self, max_size: int = 12):
        self.max_size = max_size
        self.cache: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve value and move to end (most recently used)."""
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: str, value: Any) -> None:
        """Insert/update value and move to end. Evict LRU if at capacity."""
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)


# ============================================================================
# Graph Session
# ============================================================================

@dataclass
class GraphSession:
    """Encapsulates per-session graph state."""
    active_graph: Optional[tuple[str, str]] = None


# ============================================================================
# Global State
# ============================================================================

mcp = FastMCP(name="codegrapher_mcp")

# Root of the multi-project graphs directory (set at startup from --graphs)
graphs_root: Path = Path()

# Session state for active graph selection.
# NOTE: This is process-level state shared across all sessions connected to
# this server instance. Setting the active graph affects all concurrent callers.
_session: GraphSession = GraphSession()

# LRU cache — keys are "project/graph-name/tier_name" to avoid collisions
# across graphs. Default size 12 covers ~2-3 graphs with all tiers cached.
cache: LRUCache = LRUCache()


# ============================================================================
# Helper Functions
# ============================================================================

def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    import os
    parser = argparse.ArgumentParser(description="CodeGrapher MCP Server")
    parser.add_argument(
        "--graphs",
        type=str,
        default=os.environ.get("CODEGRAPHER_GRAPHS", "./graphs"),
        help="Path to graphs root directory (default: $CODEGRAPHER_GRAPHS or ./graphs)",
    )
    parser.add_argument(
        "--max-cached-tiers",
        type=int,
        default=12,
        help="Maximum number of tier files to cache in memory (default: 12)",
    )
    return parser.parse_args()


def _init(graphs_path: Path, max_cached_tiers: int) -> None:
    """Validate graphs root and initialize cache. Does NOT load any graph."""
    global graphs_root, cache

    if not graphs_path.exists():
        # Non-fatal: server starts, tools return errors until graphs are built
        print(f"[WARN] Graphs root directory not found: {graphs_path}", file=sys.stderr)

    graphs_root = graphs_path
    cache = LRUCache(max_cached_tiers)


def _resolve_graph(graph_override: Optional[str] = None) -> tuple[Path, dict[str, Any]]:
    """
    Resolve which graph to use for a tool call.

    Priority: graph_override param > active_graph global > error.

    Args:
        graph_override: Optional "project/graph-name" string from the tool call.

    Returns:
        (graph_dir, toc) — graph_dir is the Path to the graph directory,
        toc is the parsed toc.json for that graph.

    Raises:
        ValueError: If no graph is selected and no override is provided.
        FileNotFoundError: If the resolved path has no toc.json.
    """
    global graphs_root

    if graph_override:
        parts = graph_override.strip("/").split("/")
        if len(parts) != 2:
            raise ValueError(
                f"Invalid graph parameter '{graph_override}'. "
                "Expected format: 'project/graph-name' (e.g. 'myproject/overview')"
            )
        project, graph = parts
    elif _session.active_graph is not None:
        project, graph = _session.active_graph
    else:
        raise ValueError(
            "No graph selected. Use set_active_graph(project, graph) to set one for this "
            "session, or pass graph='project/graph-name' on individual tool calls. "
            "Use list_projects() to see available projects."
        )

    graph_dir = graphs_root / project / graph
    toc_path = graph_dir / "toc.json"
    if not toc_path.exists():
        raise FileNotFoundError(
            f"toc.json not found at {toc_path}. "
            f"Check that '{project}/{graph}' is a valid graph path under {graphs_root}. "
            "Use list_graphs(project) to see available graphs."
        )

    with open(toc_path, "r") as f:
        toc = json.load(f)

    return graph_dir, toc


def _get_tier(tier_name: str, graph_dir: Path, toc: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve tier data from cache or disk.
    Builds and caches adjacency indices (nodes_by_id, outgoing, incoming).
    Cache key includes graph path to avoid collisions across graphs.
    """
    cache_key = f"{graph_dir.relative_to(graphs_root).as_posix()}/{tier_name}"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    tier_files = toc.get("tier_files", {})
    filename = tier_files.get(tier_name)
    if not filename:
        raise ValueError(f"Tier '{tier_name}' not found in toc.json")

    tier_path = graph_dir / filename
    if not tier_path.exists():
        raise FileNotFoundError(f"Tier file not found: {tier_path}")

    with open(tier_path, "r") as f:
        tier_data = json.load(f)

    tier_data["_index"] = GraphIndex(tier_data)
    cache.put(cache_key, tier_data)
    return tier_data


def _get_index(tier_name: str, graph_dir: Path, toc: dict[str, Any]) -> GraphIndex:
    """Retrieve adjacency index for a tier."""
    tier_data = _get_tier(tier_name, graph_dir, toc)
    return tier_data["_index"]


# ============================================================================
# Tool Input Models
# ============================================================================

_GRAPH_FIELD = Field(
    default=None,
    description=(
        "Graph to query, as 'project/graph-name' (e.g. 'myproject/overview'). "
        "Overrides the active graph for this call only. "
        "If omitted, uses the active graph set by set_active_graph."
    ),
)


class ExpandNodeInput(BaseModel):
    node_id: str = Field(description="Full node ID (e.g., 'stress::path/file.cc::SymbolName')")
    graph: Optional[str] = _GRAPH_FIELD


class FindTypeInput(BaseModel):
    type_name: str = Field(description="Type name substring to search for (case-insensitive)")
    graph: Optional[str] = _GRAPH_FIELD


class FindSymbolInput(BaseModel):
    name_substring: str = Field(description="Symbol name substring to search for (case-insensitive)")
    graph: Optional[str] = _GRAPH_FIELD


class GetFileSymbolsInput(BaseModel):
    file_path: str = Field(description="File path substring to match (case-insensitive, e.g. 'broker/relay.cc')")
    graph: Optional[str] = _GRAPH_FIELD


class SearchInput(BaseModel):
    name_substring: str = Field(description="Label substring to search for across both SYMBOL and TYPE nodes (case-insensitive)")
    graph: Optional[str] = _GRAPH_FIELD


class TraceDataFlowInput(BaseModel):
    from_node_id: str = Field(description="Source node ID")
    to_node_id: str = Field(description="Target node ID (ignored for topological algorithm)")
    algorithm: str = Field(
        default="data_flow",
        description="Pathfinding algorithm: data_flow|bfs|dfs|bidirectional_bfs|dijkstra|topological",
    )
    max_depth: int = Field(default=10, description="Maximum search depth")
    graph: Optional[str] = _GRAPH_FIELD


class SummarizeEntryPointInput(BaseModel):
    entry_point_id: str = Field(
        description="Node ID of the entry point file or symbol (e.g., 'repo::Client_Side/main.py')"
    )
    max_hops: int = Field(
        default=3,
        description="Maximum call-edge hops to traverse from the entry point (default: 3)"
    )
    follow_relations: list[str] = Field(
        default=["calls"],
        description="Edge relation types to follow during BFS (default: ['calls']). Include 'produces' and 'consumes' for data-pipeline style codebases."
    )
    graph: Optional[str] = _GRAPH_FIELD


class ListGraphsInput(BaseModel):
    project: str = Field(description="Project name (a directory under the graphs root)")


class SetActiveGraphInput(BaseModel):
    project: str = Field(description="Project name (directory under graphs root)")
    graph: str = Field(description="Graph name (directory under the project, e.g. 'overview' or 'auth-subsystem')")


# ============================================================================
# Graph Navigation Tools
# ============================================================================

@mcp.tool(
    name="list_projects",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_projects() -> dict[str, Any]:
    """
    List all project directories under the graphs root.

    Returns the names of every subdirectory directly under the graphs root.
    Each name is a valid 'project' argument for list_graphs and set_active_graph.

    Use this as the starting point when you don't know which projects are available,
    or to confirm a project name before calling list_graphs.
    """
    if not graphs_root.exists():
        return {"error": f"Graphs root not found: {graphs_root}"}
    projects = sorted(d.name for d in graphs_root.iterdir() if d.is_dir())
    return {"graphs_root": str(graphs_root), "projects": projects, "count": len(projects)}


@mcp.tool(
    name="list_graphs",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_graphs(input: ListGraphsInput) -> dict[str, Any]:
    """
    List all graphs available under a project, with metadata from each graph's toc.json.

    For each graph directory found under '<graphs_root>/<project>/', returns:
    - graph_name: directory name — use as the 'graph' part of 'project/graph-name'
    - feature: feature name stored in toc.json
    - generated: build timestamp from toc.json
    - entry_point_count: number of detected entry points
    - tier_files: list of tier names available (e.g. ["file", "symbol", "directory", "repo"])

    Use list_projects() first to discover valid project names.
    """
    project_dir = graphs_root / input.project
    if not project_dir.exists():
        return {
            "error": f"Project '{input.project}' not found under {graphs_root}",
            "hint": "Use list_projects() to see available projects",
        }
    graphs = []
    for d in sorted(project_dir.iterdir()):
        if not d.is_dir():
            continue
        toc_path = d / "toc.json"
        if not toc_path.exists():
            continue
        with open(toc_path, "r") as f:
            t = json.load(f)
        graphs.append({
            "graph_name": d.name,
            "feature": t.get("feature", ""),
            "generated": t.get("generated", ""),
            "entry_point_count": len(t.get("entry_points", [])),
            "tier_files": list(t.get("tier_files", {}).keys()),
        })
    return {"project": input.project, "graphs": graphs, "count": len(graphs)}


@mcp.tool(
    name="set_active_graph",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def set_active_graph(input: SetActiveGraphInput) -> dict[str, Any]:
    """
    Set the active graph for all subsequent tool calls in this session.

    Once set, all query tools (find_symbol, expand_node, search, etc.) will use
    this graph automatically without requiring a 'graph' parameter on each call.
    This is the preferred mode for focused exploration of a single graph.

    Individual tools can still override this for a single call by passing their
    own graph='project/graph-name' parameter — that override does not change
    the active graph.

    Validates that the target graph directory exists and contains a valid toc.json
    before accepting the selection.

    NOTE: The active graph is process-level state. If multiple Claude sessions share
    one MCP server process, set_active_graph affects all of them simultaneously.
    Use per-call graph= overrides if working across multiple graphs concurrently.
    """
    graph_dir = graphs_root / input.project / input.graph
    toc_path = graph_dir / "toc.json"
    if not toc_path.exists():
        return {
            "error": f"Graph '{input.project}/{input.graph}' not found or has no toc.json",
            "hint": "Use list_graphs(project) to see available graphs",
        }
    _session.active_graph = (input.project, input.graph)
    with open(toc_path, "r") as f:
        toc = json.load(f)
    return {
        "active_graph": f"{input.project}/{input.graph}",
        "feature": toc.get("feature", ""),
        "generated": toc.get("generated", ""),
        "entry_point_count": len(toc.get("entry_points", [])),
        "tier_files": list(toc.get("tier_files", {}).keys()),
        "graph_dir": str(graph_dir),
    }


@mcp.tool(
    name="get_active_graph",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_active_graph() -> dict[str, Any]:
    """
    Return the currently active graph and its toc.json summary.

    Shows which graph will be used by all query tools when no 'graph' parameter
    is explicitly provided on a call. Returns status='not_set' with instructions
    if no active graph has been selected yet.

    Use this at the start of a session to confirm which graph is loaded, or
    after set_active_graph to verify the selection took effect.
    """
    if _session.active_graph is None:
        return {
            "status": "not_set",
            "message": (
                "No active graph selected. "
                "Call set_active_graph(project, graph) to select one for this session, "
                "or pass graph='project/graph-name' on individual tool calls. "
                "Use list_projects() to see available projects."
            ),
        }
    project, graph = _session.active_graph
    graph_dir = graphs_root / project / graph
    toc_path = graph_dir / "toc.json"
    if not toc_path.exists():
        return {
            "status": "stale",
            "active_graph": f"{project}/{graph}",
            "error": "Previously active graph no longer exists on disk. Call set_active_graph again.",
        }
    with open(toc_path, "r") as f:
        toc = json.load(f)
    return {
        "status": "active",
        "active_graph": f"{project}/{graph}",
        "graph_dir": str(graph_dir),
        "feature": toc.get("feature", ""),
        "generated": toc.get("generated", ""),
        "entry_point_count": len(toc.get("entry_points", [])),
        "tier_files": list(toc.get("tier_files", {}).keys()),
    }


# ============================================================================
# Graph Query Tools
# ============================================================================

@mcp.tool(
    name="list_entry_points",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_entry_points(graph: Optional[str] = None) -> dict[str, Any]:
    """
    List all entry points detected in the analyzed codebase.

    This is typically the first query tool to call after set_active_graph,
    providing the main symbols and files that serve as starting points for
    graph exploration.

    Returns entry_points list from toc.json without loading tier files.

    Args:
        graph: Optional 'project/graph-name' override for this call only.
    """
    try:
        graph_dir, toc = _resolve_graph(graph)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}
    return {
        "feature": toc.get("feature", ""),
        "generated": toc.get("generated", ""),
        "entry_points": toc.get("entry_points", []),
    }


@mcp.tool(
    name="get_feature_summary",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_feature_summary(graph: Optional[str] = None) -> dict[str, Any]:
    """
    Get high-level summary of the analyzed feature/graph.

    Provides:
    - feature name and generation timestamp
    - entry points
    - node counts by type (file, symbol, type) and total
    - edge count
    - list of all files with their language and type

    Uses tier_file (for file/symbol nodes) and tier_symbol (for edge count).

    Args:
        graph: Optional 'project/graph-name' override for this call only.
    """
    try:
        graph_dir, toc = _resolve_graph(graph)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}

    tier_file_data = _get_tier("file", graph_dir, toc)
    file_nodes = [n for n in tier_file_data.get("nodes", []) if n.get("type") == "file"]

    tier_symbol_data = _get_tier("symbol", graph_dir, toc)
    symbol_nodes = [n for n in tier_symbol_data.get("nodes", []) if n.get("type") == "symbol"]
    type_nodes = [n for n in tier_symbol_data.get("nodes", []) if n.get("type") == "type"]
    edge_count = len(tier_symbol_data.get("edges", []))

    files_list = [
        {
            "id": n["id"],
            "label": n.get("label", ""),
            "file": n.get("file", ""),
            "language": n.get("language", "unknown"),
        }
        for n in file_nodes
    ]

    return {
        "feature": toc.get("feature", ""),
        "generated": toc.get("generated", ""),
        "entry_points": toc.get("entry_points", []),
        "node_counts": {
            "file": len(file_nodes),
            "symbol": len(symbol_nodes),
            "type": len(type_nodes),
            "total": len(file_nodes) + len(symbol_nodes) + len(type_nodes),
        },
        "edge_count": edge_count,
        "files": files_list,
    }


@mcp.tool(
    name="expand_node",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def expand_node(input: ExpandNodeInput) -> dict[str, Any]:
    """
    Expand a single node to show all incoming and outgoing edges.

    Given a node ID (e.g., 'stress::path/file.cc::SymbolName'), return:
    - Full node details (id, type, label, file, line, language, etc.)
    - Outgoing edges (what this node produces/calls/references)
    - Incoming edges (what produces/calls/references this node)
    - Total neighbor count

    Useful for understanding a symbol's dependencies and dependents.

    Returns an error if the node does not exist in the symbol tier.
    """
    try:
        graph_dir, toc = _resolve_graph(input.graph)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}

    node_id = input.node_id
    tier_symbol_data = _get_tier("symbol", graph_dir, toc)
    index = _get_index("symbol", graph_dir, toc)
    nodes_by_id = index.nodes_by_id
    outgoing = index.outgoing
    incoming = index.incoming

    node = nodes_by_id.get(node_id)
    if not node:
        return {
            "error": f"Node not found: {node_id}",
            "hint": "Use list_entry_points or get_feature_summary to find valid node IDs",
        }

    outgoing_formatted = []
    for edge in outgoing.get(node_id, []):
        target_id = edge.get("to")
        target_node = nodes_by_id.get(target_id, {})
        outgoing_formatted.append({
            "relation": edge.get("relation", ""),
            "target_id": target_id,
            "target_label": target_node.get("label", ""),
            "target_type": target_node.get("type", ""),
        })

    incoming_formatted = []
    for edge in incoming.get(node_id, []):
        source_id = edge.get("from")
        source_node = nodes_by_id.get(source_id, {})
        incoming_formatted.append({
            "relation": edge.get("relation", ""),
            "source_id": source_id,
            "source_label": source_node.get("label", ""),
            "source_type": source_node.get("type", ""),
        })

    return {
        "node": node,
        "outgoing": outgoing_formatted,
        "incoming": incoming_formatted,
        "neighbor_count": len(outgoing_formatted) + len(incoming_formatted),
    }


@mcp.tool(
    name="find_type",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def find_type(input: FindTypeInput) -> list[dict[str, Any]]:
    """
    Find all type nodes matching a substring (case-insensitive).

    For each match, return:
    - Full node details
    - Producers: nodes that produce (define) this type
    - Consumers: nodes that consume (use) this type
    - Typedef chain: all nodes reachable via typedef_of edges (BFS, max depth 10)

    Useful for understanding type definitions, usages, and type aliases.

    Returns empty list if no matches found.
    """
    try:
        graph_dir, toc = _resolve_graph(input.graph)
    except (ValueError, FileNotFoundError) as e:
        return [{"error": str(e)}]

    search_term = input.type_name.lower()
    tier_symbol_data = _get_tier("symbol", graph_dir, toc)
    index = _get_index("symbol", graph_dir, toc)
    nodes_by_id = index.nodes_by_id
    outgoing = index.outgoing
    incoming = index.incoming

    nodes = tier_symbol_data.get("nodes", [])
    matching_types = [
        n for n in nodes
        if n.get("type") == "type" and search_term in n.get("label", "").lower()
    ]

    results = []
    for type_node in matching_types:
        type_id = type_node["id"]

        producers = []
        for edge in incoming.get(type_id, []):
            if edge.get("relation") == "produces":
                source_id = edge.get("from")
                source_node = nodes_by_id.get(source_id, {})
                producers.append({
                    "id": source_id,
                    "label": source_node.get("label", ""),
                    "type": source_node.get("type", ""),
                })

        consumers = []
        for edge in incoming.get(type_id, []):
            if edge.get("relation") == "consumes":
                source_id = edge.get("from")
                source_node = nodes_by_id.get(source_id, {})
                consumers.append({
                    "id": source_id,
                    "label": source_node.get("label", ""),
                    "type": source_node.get("type", ""),
                })

        typedef_chain = _bfs_typedef_chain(type_id, nodes_by_id, outgoing, incoming, max_depth=10)

        results.append({
            "node": type_node,
            "producers": producers,
            "consumers": consumers,
            "typedef_chain": typedef_chain,
        })

    return results


def _bfs_typedef_chain(
    start_id: str,
    nodes_by_id: dict[str, Any],
    outgoing: dict[str, list[dict]],
    incoming: dict[str, list[dict]],
    max_depth: int = 10,
) -> list[dict[str, Any]]:
    """
    BFS following typedef_of edges in both directions (up to max_depth).
    Returns flat list of reachable nodes.
    """
    visited = {start_id}
    queue = deque([(start_id, 0)])
    result = []

    while queue:
        node_id, depth = queue.popleft()
        if depth > max_depth:
            continue

        node = nodes_by_id.get(node_id, {})
        result.append({"id": node_id, "label": node.get("label", "")})

        for edge in outgoing.get(node_id, []):
            if edge.get("relation") == "typedef_of":
                next_id = edge.get("to")
                if next_id and next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, depth + 1))

        for edge in incoming.get(node_id, []):
            if edge.get("relation") == "typedef_of":
                next_id = edge.get("from")
                if next_id and next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, depth + 1))

    return result


@mcp.tool(
    name="find_symbol",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def find_symbol(input: FindSymbolInput) -> list[dict[str, Any]]:
    """
    Find all symbol nodes matching a name substring (case-insensitive).

    For each match, return:
    - Full node details (id, type, label, file, line, language, etc.)
    - Outgoing edges (what this symbol calls/produces/references)
    - Incoming edges (what calls/references this symbol)

    Useful when you know a function or method name but not its full node ID.

    Returns empty list if no matches found.
    """
    try:
        graph_dir, toc = _resolve_graph(input.graph)
    except (ValueError, FileNotFoundError) as e:
        return [{"error": str(e)}]

    search_term = input.name_substring.lower()
    tier_symbol_data = _get_tier("symbol", graph_dir, toc)
    index = _get_index("symbol", graph_dir, toc)
    nodes_by_id = index.nodes_by_id
    outgoing = index.outgoing
    incoming = index.incoming

    nodes = tier_symbol_data.get("nodes", [])
    matching = [
        n for n in nodes
        if n.get("type") == "symbol" and search_term in n.get("label", "").lower()
    ]

    results = []
    for sym_node in matching:
        sym_id = sym_node["id"]

        outgoing_edges = []
        for edge in outgoing.get(sym_id, []):
            target_id = edge.get("to")
            target_node = nodes_by_id.get(target_id, {})
            outgoing_edges.append({
                "relation": edge.get("relation", ""),
                "target_id": target_id,
                "target_label": target_node.get("label", ""),
                "target_type": target_node.get("type", ""),
            })

        incoming_edges = []
        for edge in incoming.get(sym_id, []):
            source_id = edge.get("from")
            source_node = nodes_by_id.get(source_id, {})
            incoming_edges.append({
                "relation": edge.get("relation", ""),
                "source_id": source_id,
                "source_label": source_node.get("label", ""),
                "source_type": source_node.get("type", ""),
            })

        results.append({
            "node": sym_node,
            "outgoing": outgoing_edges,
            "incoming": incoming_edges,
        })

    return results


@mcp.tool(
    name="search",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def search(input: SearchInput) -> dict[str, Any]:
    """
    Search for nodes matching a label substring across both SYMBOL and TYPE nodes (case-insensitive).

    Returns two lists:
    - symbols: matching symbol nodes with their incoming/outgoing edges
    - types: matching type nodes with their incoming/outgoing edges

    Use this when you don't know whether the thing you're looking for is a
    symbol (function/class/method) or a type (message/struct/alias).
    Use find_symbol or find_type if you already know which kind.

    Returns empty lists if no matches found.
    """
    try:
        graph_dir, toc = _resolve_graph(input.graph)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}

    search_term = input.name_substring.lower()
    tier_symbol_data = _get_tier("symbol", graph_dir, toc)
    index = _get_index("symbol", graph_dir, toc)
    nodes_by_id = index.nodes_by_id
    outgoing = index.outgoing
    incoming = index.incoming

    nodes = tier_symbol_data.get("nodes", [])
    matching = [
        n for n in nodes
        if n.get("type") in ("symbol", "type") and search_term in n.get("label", "").lower()
    ]

    def _format_node(node: dict) -> dict:
        nid = node["id"]
        out_edges = []
        for edge in outgoing.get(nid, []):
            target_id = edge.get("to")
            target_node = nodes_by_id.get(target_id, {})
            out_edges.append({
                "relation": edge.get("relation", ""),
                "target_id": target_id,
                "target_label": target_node.get("label", ""),
                "target_type": target_node.get("type", ""),
            })
        in_edges = []
        for edge in incoming.get(nid, []):
            source_id = edge.get("from")
            source_node = nodes_by_id.get(source_id, {})
            in_edges.append({
                "relation": edge.get("relation", ""),
                "source_id": source_id,
                "source_label": source_node.get("label", ""),
                "source_type": source_node.get("type", ""),
            })
        return {"node": node, "outgoing": out_edges, "incoming": in_edges}

    symbols = [_format_node(n) for n in matching if n.get("type") == "symbol"]
    types = [_format_node(n) for n in matching if n.get("type") == "type"]

    return {
        "symbols": symbols,
        "types": types,
        "symbol_count": len(symbols),
        "type_count": len(types),
        "total_count": len(symbols) + len(types),
    }


@mcp.tool(
    name="get_file_symbols",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_file_symbols(input: GetFileSymbolsInput) -> dict[str, Any]:
    """
    Return all symbols defined in a file (matched by file path substring).

    For each symbol, return its full node details and outgoing edges.
    Also returns any type nodes defined in the matched file.

    Useful as a one-call shortcut instead of get_feature_summary + repeated expand_node calls.

    Returns error if no file matches the path substring.
    """
    try:
        graph_dir, toc = _resolve_graph(input.graph)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}

    search_term = input.file_path.lower()
    tier_symbol_data = _get_tier("symbol", graph_dir, toc)
    index = _get_index("symbol", graph_dir, toc)
    nodes_by_id = index.nodes_by_id
    outgoing = index.outgoing

    nodes = tier_symbol_data.get("nodes", [])

    matched_files = [
        n for n in nodes
        if n.get("type") == "file" and search_term in n.get("file", "").lower()
    ]

    if not matched_files:
        return {
            "error": f"No file found matching: {input.file_path}",
            "hint": "Use get_feature_summary to list all files with their paths",
        }

    results = []
    for file_node in matched_files:
        file_path_val = file_node.get("file", "")
        symbols = [
            n for n in nodes
            if n.get("type") == "symbol" and n.get("file", "") == file_path_val
        ]
        types = [
            n for n in nodes
            if n.get("type") == "type" and n.get("file", "") == file_path_val
        ]

        symbol_details = []
        for sym in symbols:
            sym_id = sym["id"]
            edges = []
            for edge in outgoing.get(sym_id, []):
                target_id = edge.get("to")
                target_node = nodes_by_id.get(target_id, {})
                edges.append({
                    "relation": edge.get("relation", ""),
                    "target_id": target_id,
                    "target_label": target_node.get("label", ""),
                    "target_type": target_node.get("type", ""),
                })
            symbol_details.append({
                "node": sym,
                "outgoing": edges,
            })

        results.append({
            "file": file_node,
            "symbols": symbol_details,
            "types": types,
            "symbol_count": len(symbols),
            "type_count": len(types),
        })

    return {"matches": results, "file_count": len(results)}


@mcp.tool(
    name="trace_data_flow",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def trace_data_flow(input: TraceDataFlowInput) -> dict[str, Any]:
    """
    Find a path between two nodes using one of six algorithms.

    Algorithms:
    - data_flow (DEFAULT): BFS over produces/consumes/calls edges. Prioritizes data flow
      (produces/consumes) before calls.
    - bfs: Standard breadth-first search over all edge types (shortest hop path).
    - dfs: Depth-first search, returns first path found.
    - bidirectional_bfs: BFS from both endpoints simultaneously, meet in the middle.
    - dijkstra: Weighted shortest path (produces/consumes/typedef_of=1, calls/maps_to=2, uses_type=3, others=10).
    - topological: Reachability BFS from from_node (ignores to_node). Returns all reached nodes within max_depth.

    Returns:
    - path: list of nodes with relation_to_next showing edge type to successor
    - path_length: number of nodes in path
    - truncated: true if search hit max_depth without completing
    - message: human-readable summary

    For topological, to_node_id is ignored; the path represents all reachable nodes.
    """
    try:
        graph_dir, toc = _resolve_graph(input.graph)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}

    from_id = input.from_node_id
    to_id = input.to_node_id
    algorithm = input.algorithm
    max_depth = input.max_depth

    tier_symbol_data = _get_tier("symbol", graph_dir, toc)
    index = _get_index("symbol", graph_dir, toc)
    nodes_by_id = index.nodes_by_id
    outgoing = index.outgoing
    incoming = index.incoming

    if from_id not in nodes_by_id:
        return {
            "algorithm": algorithm,
            "path": [],
            "path_length": 0,
            "truncated": False,
            "message": f"Source node not found: {from_id}",
        }

    if algorithm != "topological" and to_id not in nodes_by_id:
        return {
            "algorithm": algorithm,
            "path": [],
            "path_length": 0,
            "truncated": False,
            "message": f"Target node not found: {to_id}",
        }

    if algorithm == "data_flow":
        result = _trace_data_flow(from_id, to_id, nodes_by_id, outgoing, incoming, max_depth)
    elif algorithm == "bfs":
        result = _trace_bfs(from_id, to_id, nodes_by_id, outgoing, max_depth)
    elif algorithm == "dfs":
        result = _trace_dfs(from_id, to_id, nodes_by_id, outgoing, max_depth)
    elif algorithm == "bidirectional_bfs":
        result = _trace_bidirectional_bfs(from_id, to_id, nodes_by_id, outgoing, incoming, max_depth)
    elif algorithm == "dijkstra":
        result = _trace_dijkstra(from_id, to_id, nodes_by_id, outgoing, max_depth)
    elif algorithm == "topological":
        result = _trace_topological(from_id, nodes_by_id, outgoing, max_depth)
    else:
        result = {
            "algorithm": algorithm,
            "path": [],
            "path_length": 0,
            "truncated": False,
            "message": f"Unknown algorithm: {algorithm}",
        }

    return result


@mcp.tool(
    name="summarize_entry_point",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def summarize_entry_point(input: SummarizeEntryPointInput) -> dict[str, Any]:
    """
    Summarize the call structure of an entry point up to max_hops deep.

    Unlike trace_data_flow (which finds a path between two known nodes),
    this tool answers: "What does this entry point do?" without requiring
    a target node.

    Returns:
    - entry_point: the resolved entry node details
    - files_touched: distinct files reachable within max_hops, sorted by
      first-encounter hop depth (closest first)
    - call_tree: per-hop breakdown — each hop lists only the NEW callees
      first reached at that depth, with cross_file flag and entry_distance
    - cross_file_edges: all edges that cross a file boundary, structured
      as {from_label, from_file, to_label, to_file, hop}
    - summary: human-readable counts

    Uses cross_file and entry_distance fields if present (written by the
    _annotate_graph post-processing pass in run.py). Degrades gracefully
    if those fields are absent.

    Tip: start with max_hops=2 for an overview; increase to 3-4 for detail.
    Use follow_relations=["calls","produces","consumes"] for data-pipeline
    codebases where data flow edges are as important as call edges.
    The cross_file_edges list is the most useful output for understanding
    multi-file features — it shows exactly where control crosses boundaries.
    """
    try:
        graph_dir, toc = _resolve_graph(input.graph)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}

    entry_id = input.entry_point_id
    max_hops = input.max_hops
    follow_relations = input.follow_relations

    tier_symbol_data = _get_tier("symbol", graph_dir, toc)
    index = _get_index("symbol", graph_dir, toc)
    nodes_by_id = index.nodes_by_id
    outgoing = index.outgoing

    entry_node = nodes_by_id.get(entry_id)
    if not entry_node:
        matches = [
            n for n in tier_symbol_data.get("nodes", [])
            if entry_id in n.get("id", "") or entry_id in n.get("file", "")
        ]
        if not matches:
            return {
                "error": f"Entry point not found: {entry_id}",
                "hint": "Use list_entry_points to find valid entry point IDs",
            }
        entry_node = matches[0]
        entry_id = entry_node["id"]

    entry_file = entry_node.get("file", "")
    entry_file_normalized = entry_file.replace("\\", "/")

    seed_ids: list[str] = []
    for node in tier_symbol_data.get("nodes", []):
        node_file = (node.get("file") or "").replace("\\", "/")
        if node_file == entry_file_normalized:
            seed_ids.append(node["id"])

    if not seed_ids:
        seed_ids = [entry_id]

    visited: dict[str, int] = {}
    for sid in seed_ids:
        visited[sid] = 0

    hop_nodes: dict[int, list[str]] = {0: list(seed_ids)}

    queue = deque([(sid, 0) for sid in seed_ids])
    follow_set = set(follow_relations)
    while queue:
        node_id, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for edge in outgoing.get(node_id, []):
            if edge.get("relation") not in follow_set:
                continue
            next_id = edge.get("to")
            if not next_id or next_id in visited:
                continue
            next_hop = depth + 1
            visited[next_id] = next_hop
            hop_nodes.setdefault(next_hop, []).append(next_id)
            queue.append((next_id, next_hop))

    file_min_hop: dict[str, int] = {}
    for node_id, hop in visited.items():
        node = nodes_by_id.get(node_id, {})
        f = (node.get("file") or "").replace("\\", "/")
        if f and f != entry_file_normalized:
            if f not in file_min_hop or hop < file_min_hop[f]:
                file_min_hop[f] = hop

    files_touched = sorted(
        [{"file": f, "first_reached_at_hop": h} for f, h in file_min_hop.items()],
        key=lambda x: (x["first_reached_at_hop"], x["file"])
    )

    call_tree: dict[str, list[dict]] = {}
    for hop in range(0, max_hops + 1):
        nodes_at_hop = hop_nodes.get(hop, [])
        hop_entries = []
        for node_id in nodes_at_hop:
            node = nodes_by_id.get(node_id, {})
            hop_entries.append({
                "node_id": node_id,
                "label": node.get("label", ""),
                "file": (node.get("file") or "").replace("\\", "/"),
                "entry_distance": node.get("entry_distance"),
            })
        if hop_entries:
            call_tree[f"hop_{hop}"] = hop_entries

    cross_file_edges: list[dict] = []
    seen_cross: set[tuple[str, str]] = set()
    for node_id in visited:
        for edge in outgoing.get(node_id, []):
            if not edge.get("cross_file", False):
                continue
            from_id = edge.get("from", "")
            to_id = edge.get("to", "")
            if to_id not in visited:
                continue
            key = (from_id, to_id)
            if key in seen_cross:
                continue
            seen_cross.add(key)
            from_node = nodes_by_id.get(from_id, {})
            to_node = nodes_by_id.get(to_id, {})
            cross_file_edges.append({
                "from_label": from_node.get("label", ""),
                "from_file": (from_node.get("file") or "").replace("\\", "/"),
                "to_label": to_node.get("label", ""),
                "to_file": (to_node.get("file") or "").replace("\\", "/"),
                "relation": edge.get("relation", ""),
                "hop": visited.get(from_id, -1),
            })

    cross_file_edges.sort(key=lambda x: (x["hop"], x["from_file"], x["to_file"]))

    return {
        "entry_point": {
            "node_id": entry_id,
            "label": entry_node.get("label", ""),
            "file": entry_file_normalized,
            "entry_distance": entry_node.get("entry_distance"),
        },
        "files_touched": files_touched,
        "call_tree": call_tree,
        "cross_file_edges": cross_file_edges,
        "summary": {
            "total_nodes_reached": len(visited),
            "files_touched_count": len(files_touched),
            "cross_file_edge_count": len(cross_file_edges),
            "max_hops": max_hops,
        },
    }


# ============================================================================
# Pathfinding Helpers (unchanged)
# ============================================================================

def _trace_data_flow(
    from_id: str,
    to_id: str,
    nodes_by_id: dict[str, Any],
    outgoing: dict[str, list[dict]],
    incoming: dict[str, list[dict]],
    max_depth: int,
) -> dict[str, Any]:
    """Edge-typed BFS prioritizing data flow edges (produces/consumes) over calls."""
    visited = {from_id}
    queue = deque([(from_id, 0, [])])

    while queue:
        node_id, depth, path = queue.popleft()

        if node_id == to_id:
            formatted_path = _format_path(path, nodes_by_id)
            return {
                "algorithm": "data_flow",
                "path": formatted_path,
                "path_length": len(formatted_path),
                "truncated": False,
                "message": f"Path found: {len(formatted_path) - 1} hop(s) via data flow",
            }

        if depth >= max_depth:
            continue

        neighbors = outgoing.get(node_id, [])
        data_flow_edges = [e for e in neighbors if e.get("relation") in {"produces", "consumes"}]
        call_edges = [e for e in neighbors if e.get("relation") == "calls"]
        sorted_neighbors = data_flow_edges + call_edges

        for edge in sorted_neighbors:
            next_id = edge.get("to")
            if next_id and next_id not in visited:
                visited.add(next_id)
                new_path = path + [(node_id, edge.get("relation"), next_id)]
                queue.append((next_id, depth + 1, new_path))

    return {
        "algorithm": "data_flow",
        "path": [],
        "path_length": 0,
        "truncated": False,
        "message": f"No path found from {nodes_by_id.get(from_id, {}).get('label', from_id)} to {nodes_by_id.get(to_id, {}).get('label', to_id)}",
    }


def _trace_bfs(
    from_id: str,
    to_id: str,
    nodes_by_id: dict[str, Any],
    outgoing: dict[str, list[dict]],
    max_depth: int,
) -> dict[str, Any]:
    """Standard BFS over all edge types."""
    visited = {from_id}
    queue = deque([(from_id, 0, [])])

    while queue:
        node_id, depth, path = queue.popleft()

        if node_id == to_id:
            formatted_path = _format_path(path, nodes_by_id)
            return {
                "algorithm": "bfs",
                "path": formatted_path,
                "path_length": len(formatted_path),
                "truncated": False,
                "message": f"Path found: {len(formatted_path) - 1} hop(s) via BFS",
            }

        if depth >= max_depth:
            continue

        for edge in outgoing.get(node_id, []):
            next_id = edge.get("to")
            if next_id and next_id not in visited:
                visited.add(next_id)
                new_path = path + [(node_id, edge.get("relation"), next_id)]
                queue.append((next_id, depth + 1, new_path))

    return {
        "algorithm": "bfs",
        "path": [],
        "path_length": 0,
        "truncated": False,
        "message": f"No path found from {nodes_by_id.get(from_id, {}).get('label', from_id)} to {nodes_by_id.get(to_id, {}).get('label', to_id)}",
    }


def _trace_dfs(
    from_id: str,
    to_id: str,
    nodes_by_id: dict[str, Any],
    outgoing: dict[str, list[dict]],
    max_depth: int,
) -> dict[str, Any]:
    """Iterative DFS, returns first path found."""
    stack = [(from_id, 0, [], frozenset({from_id}))]
    truncated = False

    while stack:
        node_id, depth, path, branch_visited = stack.pop()

        if node_id == to_id:
            formatted_path = _format_path(path, nodes_by_id)
            return {
                "algorithm": "dfs",
                "path": formatted_path,
                "path_length": len(formatted_path),
                "truncated": False,
                "message": f"Path found: {len(formatted_path) - 1} hop(s) via DFS",
            }

        if depth >= max_depth:
            truncated = True
            continue

        for edge in outgoing.get(node_id, []):
            next_id = edge.get("to")
            if next_id and next_id not in branch_visited:
                new_path = path + [(node_id, edge.get("relation"), next_id)]
                stack.append((next_id, depth + 1, new_path, branch_visited | {next_id}))

    return {
        "algorithm": "dfs",
        "path": [],
        "path_length": 0,
        "truncated": truncated,
        "message": f"No path found from {nodes_by_id.get(from_id, {}).get('label', from_id)} to {nodes_by_id.get(to_id, {}).get('label', to_id)}",
    }


def _trace_bidirectional_bfs(
    from_id: str,
    to_id: str,
    nodes_by_id: dict[str, Any],
    outgoing: dict[str, list[dict]],
    incoming: dict[str, list[dict]],
    max_depth: int,
) -> dict[str, Any]:
    """BFS from both endpoints simultaneously. Meet in the middle."""
    if from_id == to_id:
        return {
            "algorithm": "bidirectional_bfs",
            "path": [{"node_id": from_id, "label": nodes_by_id.get(from_id, {}).get("label", ""), "type": nodes_by_id.get(from_id, {}).get("type", ""), "relation_to_next": None}],
            "path_length": 1,
            "truncated": False,
            "message": "Source and target are the same node",
        }

    forward_visited = {from_id}
    forward_queue = deque([(from_id, 0, [])])
    forward_parents: dict[str, Optional[tuple[str, Optional[str]]]] = {from_id: None}

    backward_visited = {to_id}
    backward_queue = deque([(to_id, 0, [])])
    backward_parents: dict[str, Optional[tuple[str, Optional[str]]]] = {to_id: None}

    meeting_point = None

    while forward_queue or backward_queue:
        if forward_queue:
            node_id, depth, path = forward_queue.popleft()
            if depth < max_depth:
                for edge in outgoing.get(node_id, []):
                    next_id = edge.get("to")
                    if next_id and next_id not in forward_visited:
                        forward_visited.add(next_id)
                        forward_parents[next_id] = (node_id, edge.get("relation"))
                        forward_queue.append((next_id, depth + 1, path + [(node_id, edge.get("relation"), next_id)]))
                        if next_id in backward_visited:
                            meeting_point = next_id
                            break

        if backward_queue:
            node_id, depth, path = backward_queue.popleft()
            if depth < max_depth:
                for edge in incoming.get(node_id, []):
                    prev_id = edge.get("from")
                    if prev_id and prev_id not in backward_visited:
                        backward_visited.add(prev_id)
                        backward_parents[prev_id] = (node_id, edge.get("relation"))
                        backward_queue.append((prev_id, depth + 1, path + [(prev_id, edge.get("relation"), node_id)]))
                        if prev_id in forward_visited:
                            meeting_point = prev_id
                            break

        if meeting_point:
            break

    if meeting_point:
        forward_path = []
        node = meeting_point
        while node in forward_parents and forward_parents[node] is not None:
            prev_node, relation = forward_parents[node]  # type: ignore[misc]
            forward_path.insert(0, (prev_node, relation, node))
            node = prev_node

        backward_path = []
        node = meeting_point
        while node in backward_parents and backward_parents[node] is not None:
            next_node, relation = backward_parents[node]  # type: ignore[misc]
            backward_path.append((node, relation, next_node))
            node = next_node

        full_path = forward_path + backward_path
        formatted_path = _format_path(full_path, nodes_by_id)
        return {
            "algorithm": "bidirectional_bfs",
            "path": formatted_path,
            "path_length": len(formatted_path),
            "truncated": False,
            "message": f"Path found: {len(formatted_path) - 1} hop(s) via bidirectional BFS",
        }

    return {
        "algorithm": "bidirectional_bfs",
        "path": [],
        "path_length": 0,
        "truncated": True,
        "message": f"No path found from {nodes_by_id.get(from_id, {}).get('label', from_id)} to {nodes_by_id.get(to_id, {}).get('label', to_id)}",
    }


def _trace_dijkstra(
    from_id: str,
    to_id: str,
    nodes_by_id: dict[str, Any],
    outgoing: dict[str, list[dict]],
    max_depth: int,
) -> dict[str, Any]:
    """Weighted shortest path using heapq."""
    relation_weights = {
        "produces": 1,
        "consumes": 1,
        "typedef_of": 1,
        "calls": 2,
        "maps_to": 2,
        "uses_type": 3,
    }

    dist = {from_id: 0}
    parent = {from_id: None}
    heap = [(0, from_id, 0)]
    visited = set()

    while heap:
        d, node_id, depth = heappop(heap)

        if node_id in visited:
            continue
        visited.add(node_id)

        if node_id == to_id:
            path = []
            current = to_id
            while parent.get(current) is not None:
                prev_node, relation = parent[current]
                path.insert(0, (prev_node, relation, current))
                current = prev_node

            formatted_path = _format_path(path, nodes_by_id)
            return {
                "algorithm": "dijkstra",
                "path": formatted_path,
                "path_length": len(formatted_path),
                "truncated": False,
                "message": f"Path found: {len(formatted_path) - 1} hop(s) via Dijkstra (cost {d})",
            }

        if depth >= max_depth:
            continue

        for edge in outgoing.get(node_id, []):
            next_id = edge.get("to")
            relation = edge.get("relation", "")
            weight = relation_weights.get(relation, 10)

            if next_id and next_id not in visited:
                new_dist = d + weight
                if next_id not in dist or new_dist < dist[next_id]:
                    dist[next_id] = new_dist
                    parent[next_id] = (node_id, relation)
                    heappush(heap, (new_dist, next_id, depth + 1))

    return {
        "algorithm": "dijkstra",
        "path": [],
        "path_length": 0,
        "truncated": False,
        "message": f"No path found from {nodes_by_id.get(from_id, {}).get('label', from_id)} to {nodes_by_id.get(to_id, {}).get('label', to_id)}",
    }


def _trace_topological(
    from_id: str,
    nodes_by_id: dict[str, Any],
    outgoing: dict[str, list[dict]],
    max_depth: int,
) -> dict[str, Any]:
    """Reachability BFS from from_id. Returns all nodes reachable within max_depth."""
    visited = {from_id}
    queue = deque([(from_id, 0)])
    path = []
    truncated = False

    while queue:
        node_id, depth = queue.popleft()

        node = nodes_by_id.get(node_id, {})
        path.append({
            "node_id": node_id,
            "label": node.get("label", ""),
            "type": node.get("type", ""),
            "relation_to_next": None,
        })

        if depth < max_depth:
            for edge in outgoing.get(node_id, []):
                next_id = edge.get("to")
                if next_id and next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, depth + 1))
        elif queue:
            truncated = True

    id_to_idx = {node["node_id"]: i for i, node in enumerate(path)}
    for i, node_dict in enumerate(path):
        node_id = node_dict["node_id"]
        for edge in outgoing.get(node_id, []):
            next_id = edge.get("to")
            if next_id in id_to_idx:
                node_dict["relation_to_next"] = edge.get("relation", "")
                break

    label = nodes_by_id.get(from_id, {}).get("label", from_id)
    return {
        "algorithm": "topological",
        "path": path,
        "path_length": len(path),
        "truncated": truncated,
        "message": f"Reachability from {label}: {len(path)} node(s) within depth {max_depth}",
    }


def _format_path(
    path: list[tuple[str, str, str]],
    nodes_by_id: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert path (list of (from_id, relation, to_id) tuples) to formatted path."""
    if not path:
        return []

    formatted = []
    for i, (from_id, relation, to_id) in enumerate(path):
        if i == 0:
            node = nodes_by_id.get(from_id, {})
            formatted.append({
                "node_id": from_id,
                "label": node.get("label", ""),
                "type": node.get("type", ""),
                "relation_to_next": relation,
            })

        node = nodes_by_id.get(to_id, {})
        formatted.append({
            "node_id": to_id,
            "label": node.get("label", ""),
            "type": node.get("type", ""),
            "relation_to_next": None,
        })

    return formatted


# ============================================================================
# Main
# ============================================================================

def main():
    args = _parse_args()
    _init(Path(args.graphs), args.max_cached_tiers)
    mcp.run()


if __name__ == "__main__":
    main()
