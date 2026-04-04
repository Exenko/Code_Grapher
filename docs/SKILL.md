# CodeGrapher Skill Reference

Quick reference for CodeGrapher command-line flags and MCP tools.

---

## run.py - CLI Flags

Build a graph from your codebase:

```bash
py CodeGrapher/run.py --feature NAME --root PATH [--files GLOB ...] [--dir SUBDIR ...] [options]
```

| Flag | Required | Description |
|------|----------|-------------|
| `--feature NAME` | Yes | Feature name (used in output filenames and node IDs) |
| `--root PATH` | Yes | Project root directory (all file paths relative to this) |
| `--files GLOB ...` | No | File glob patterns relative to `--root` (e.g. `'src/*.py'` `'tests/test_*.py'`) |
| `--dir SUBDIR ...` | No | Directory paths relative to `--root` (recursively finds all source files) |
| `--output-dir PATH` | No | Directory to write graph output (default: `./graphs`). E.g. `C:/Users/Mike/graphs/myproject/myfeature` |
| `--standalone` | No | Bake graph into self-contained HTML file (auto-on if <1000 nodes) |
| `--analyze CHOICE` | No | Run analyzer after building graph: `flow` (Mermaid flow diagram) or `type` (type tree expansion) |
| `--entry FILE` | No | Entry file for `--analyze flow` (e.g. `Client_Side/main.py`); uses first entry point from toc.json if omitted |
| `--type NAME` | No | Type/class name for `--analyze type` (e.g. `CookingSession`) |
| `--no-stdlib-calls` | No | Suppress call edges to stdlib receivers in TS/JS files |

**Supported languages:** Python, C/C++, TypeScript/JavaScript, Java, Kotlin, Protobuf, XML/WSDL

**Examples:**

```bash
# Whole project
py CodeGrapher/run.py --feature myapp --root . --dir .

# Specific subdirectory
py CodeGrapher/run.py --feature backend --root /path/to/project --dir src/backend

# Multiple patterns
py CodeGrapher/run.py --feature myapp --root . --files "src/*.py" "tests/test_*.py" --no-stdlib-calls

# With custom output directory
py CodeGrapher/run.py --feature myfeature --root /path/to/project --dir src --output-dir "C:/Users/Mike/graphs/myproject/myfeature"

# With analyzer
py CodeGrapher/run.py --feature myapp --root . --dir src --analyze flow
```

---

## MCP Server Tools (13 total)

Connect via: `codegrapher-mcp --graphs PATH`

All tools support an optional `graph="project/graph-name"` parameter to override the active graph for that call only.

### Graph Selection (call once per session)

**list_projects()** — List all project directories under graphs root.
- Returns: project names available for set_active_graph

**list_graphs(project)** — List all graphs under a project with metadata.
- Args: `project` (project name)
- Returns: graph names, feature, generation timestamp, entry point count, available tiers

**set_active_graph(project, graph)** — Set the active graph for this session.
- Args: `project`, `graph` (e.g. `"myproject"`, `"overview"`)
- Affects: all subsequent tool calls (use per-call `graph=` override to query other graphs without changing active)

**get_active_graph()** — Show which graph is currently active and its metadata.
- Returns: active_graph status, feature, generated timestamp, entry points, tier files

---

### Graph Overview (start here)

**list_entry_points()** — List all detected entry points in the codebase.
- Returns: entry point list with file paths and IDs (first tool to call after set_active_graph)

**get_feature_summary()** — High-level summary of the analyzed feature.
- Returns: entry points, node counts (by type), edge count, list of all files with language/type
- Use this to discover file IDs and node IDs for downstream queries

---

### Node Exploration

**expand_node(node_id)** — Show a node and all its incoming/outgoing edges.
- Args: `node_id` (full node ID, e.g. `'stress::path/file.cc::SymbolName'`)
- Returns: node details, outgoing edges (with relation type and target info), incoming edges
- Use when you know the exact node ID

**find_symbol(name_substring)** — Find all symbols matching a name (case-insensitive substring).
- Args: `name_substring` (function, class, method name or part of it)
- Returns: list of matching symbol nodes with their incoming/outgoing edges
- Use when you know part of a symbol name

**find_type(type_name)** — Find all types matching a name (case-insensitive substring).
- Args: `type_name` (class, struct, message name)
- Returns: type nodes, producers (nodes that define this type), consumers (nodes that use it), typedef chain (BFS over typedef_of edges, max 10 hops)
- Use to understand type definitions and aliases

**search(name_substring)** — Search both symbols and types at once.
- Args: `name_substring` (any label to search across both node types)
- Returns: separate lists for matching symbols and types with their edges
- Use when you don't know whether target is a symbol or type

**get_file_symbols(file_path)** — Return all symbols and types defined in a file.
- Args: `file_path` (file path substring, case-insensitive, e.g. `'broker/relay.cc'`)
- Returns: matched files with all their symbols, types, and outgoing edges
- Use as a shortcut to load all symbols in a file at once

---

### Data Flow Analysis

**trace_data_flow(from_node_id, to_node_id, algorithm, max_depth)** — Find a path between two nodes.
- Args:
  - `from_node_id`: source node ID
  - `to_node_id`: target node ID
  - `algorithm`: `"data_flow"` (default), `"bfs"`, `"dfs"`, `"bidirectional_bfs"`, `"dijkstra"`, `"topological"`
  - `max_depth`: max hops to search (default: 10)
- Returns: path as list of nodes with relation_to_next (edge type to successor), path_length, truncated flag, message
- Algorithms:
  - `data_flow`: prioritizes data flow edges (produces/consumes) over calls
  - `bfs`: shortest hop path over all edge types
  - `dfs`: first path found
  - `dijkstra`: weighted shortest path (data flow=1, calls=2, type usage=3, others=10)
  - `topological`: reachability from source (ignores target), returns all reachable nodes

**summarize_entry_point(entry_point_id, max_hops, follow_relations)** — Show what an entry point does.
- Args:
  - `entry_point_id`: node ID or file path (e.g. `'repo::Client_Side/main.py'`)
  - `max_hops`: call depth (default: 3; tip: start with 2)
  - `follow_relations`: edge types to follow (default: `["calls"]`; use `["calls", "produces", "consumes"]` for data pipelines)
- Returns: entry node details, files_touched (by hop depth), call_tree per hop, cross_file_edges, summary
- Use to understand a feature's structure without knowing target nodes

---

## Graph Directory Structure

Location: `C:/Users/Mike/graphs/<project>/<graph-name>/`

```
<project>/
  <graph-name>/
    toc.json                    # Table of contents (entry points, tier files, metadata)
    tier_file.json              # File-level nodes (projects, directories, files)
    tier_symbol.json            # Symbol-level nodes (symbols, types, all edges)
    tier_directory.json         # Optional: directory aggregation tier
    tier_repo.json              # Optional: repository-level tier
    sub/                        # Optional: sub-graph JSON files
```

Each tier is a separate JSON file for progressive level-of-detail loading. Query tools load only what's needed.

