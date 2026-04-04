# CodeGrapher Usage Guide

A practical guide for building graphs, organizing them, registering the MCP server, and exploring with progressive disclosure.

---

## 1. Building a Graph

### Basic Command

```bash
cd /path/to/your/project

python CodeGrapher/run.py \
  --feature myfeature \
  --root . \
  --dir src
```

This parses `src/` (and subdirectories) and writes output to `./graphs/`.

### Specifying Output Directory (Recommended)

Use `--output-dir` to centralize graphs in a global location:

```bash
python CodeGrapher/run.py \
  --feature myfeature \
  --root /path/to/project \
  --dir src \
  --output-dir "C:/Users/Mike/graphs/myproject/myfeature"
```

This creates:
```
C:/Users/Mike/graphs/
  myproject/
    myfeature/
      toc.json
      tier_symbol.json
      tier_file.json
      ...
```

### Multiple Input Patterns

Combine `--files` and `--dir`:

```bash
python CodeGrapher/run.py \
  --feature myapp \
  --root /path/to/project \
  --files "src/**/*.py" "tests/test_*.py" \
  --dir docs \
  --output-dir "C:/Users/Mike/graphs/myproject/myapp"
```

### Command Cheat Sheet

| Goal | Command |
|------|---------|
| Single directory | `--dir src` |
| Multiple directories | `--dir src tests lib` |
| Glob patterns | `--files "src/*.py" "tests/test_*.py"` |
| Whole project | `--dir .` |
| Suppress stdlib noise | add `--no-stdlib-calls` |

---

## 2. Global Graphs Directory Structure

Once you've built several graphs, your graphs directory looks like:

```
C:/Users/Mike/graphs/
  myproject/
    myfeature/
      toc.json                          # Table of contents
      tier_symbol.json                  # Symbols, types, all edges
      tier_file.json                    # Files, dirs, coarse edges
      viewer_myfeature.html             # Standalone viewer (if <1000 nodes)
    overview/
      toc.json
      tier_symbol.json
      tier_file.json
  anotherapp/
    backend/
      toc.json
      tier_symbol.json
      tier_file.json
    frontend/
      toc.json
      tier_symbol.json
      tier_file.json
```

**Key points:**
- Each graph lives in `<project>/<graph-name>/`
- `toc.json` is the entry point (lists entry points, tier files, metadata)
- Tier files are separate JSON documents for progressive loading
- The same physical location is used by both the web viewer and MCP server

---

## 3. MCP Server Registration

### Start the MCP Server

```bash
codegrapher-mcp --graphs "C:/Users/Mike/graphs"
```

This starts an MCP server listening for tool calls and discovers all graphs under that root.

### Connect from Claude

In Claude Desktop settings (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "codegrapher": {
      "command": "codegrapher-mcp",
      "args": ["--graphs", "C:/Users/Mike/graphs"]
    }
  }
}
```

Then in Claude, you'll have access to all 13 MCP tools.

### Connect from Claude Code

In your Claude Code session, the tools are automatically available if the MCP server is running on your system.

---

## 4. Session Setup: When to Use set_active_graph

### Option A: Single-Graph Session (Recommended)

If you're exploring one graph for a while, set it once:

```
User: I have a CodeGrapher analysis ready. Let's explore the backend of myproject.

Claude: I'll set the active graph.
> set_active_graph(project="myproject", graph="backend")

Now all subsequent tool calls use myproject/backend automatically.
```

**Advantages:**
- No need to pass `graph=` on every call
- Faster, cleaner interaction
- Session-wide context

### Option B: Cross-Graph Spot Checks

If you're comparing graphs or switching between projects, use per-call overrides:

```
set_active_graph(project="myproject", graph="backend")  # Set baseline

# Now query different graphs without changing active:
expand_node(node_id="...", graph="myproject/overview")   # Peek at overview
expand_node(node_id="...", graph="anotherapp/core")      # Check another project
expand_node(node_id="...")                                # Back to backend
```

---

## 5. Progressive Disclosure Workflow

CodeGrapher tiers are designed for step-by-step exploration. Follow this pattern:

### Step 1: Get Oriented (Overview Tier)

```
list_entry_points()
get_feature_summary()
```

Output tells you:
- What are the entry points (main files, components)?
- How many files, symbols, types in the graph?
- Which languages are present?

**Action:** Pick an entry point to start with.

### Step 2: Explore Entry Points (Symbol Tier)

```
summarize_entry_point(
  entry_point_id="repo::Client_Side/main.py",
  max_hops=2,
  follow_relations=["calls"]
)
```

Output tells you:
- What files does this entry point touch?
- What are the call chains?
- Where do control flow boundaries cross?

**Action:** Notice which symbols are called most. Pick a key symbol to expand.

### Step 3: Drill into Symbols (Symbol Tier)

```
find_symbol(name_substring="MyClass")
expand_node(node_id="feature::MyClass::method")
```

Output tells you:
- What does this symbol call?
- What calls this symbol?
- Type information and dependencies?

**Action:** Follow calls to other symbols, understanding the call graph.

### Step 4: Understand Types (Symbol Tier)

```
find_type(type_name="MyClass")
```

Output tells you:
- Who defines this type?
- Who uses this type?
- Type aliases and inheritance chain?

**Action:** Trace data flow through type constructors and consumers.

### Step 5: Find Paths Between Nodes (Symbol Tier)

```
trace_data_flow(
  from_node_id="feature::request_handler",
  to_node_id="feature::database",
  algorithm="data_flow",
  max_depth=10
)
```

Output tells you:
- How does data flow from input to storage?
- What intermediate processing steps exist?
- Which path is shortest?

**Action:** Answer "where does this request go?" questions.

---

## 6. All 13 MCP Tools at a Glance

### Navigation (4 tools)
1. **list_projects()** — See all available projects
2. **list_graphs(project)** — See all graphs in a project
3. **set_active_graph(project, graph)** — Select a graph for this session
4. **get_active_graph()** — Check which graph is active

### Overview (2 tools)
5. **list_entry_points()** — Entry point list (starting points for exploration)
6. **get_feature_summary()** — Node counts, files, edge count, entry points

### Node Search (4 tools)
7. **expand_node(node_id)** — Show node and all edges (incoming + outgoing)
8. **find_symbol(name_substring)** — Search for symbols by name
9. **find_type(type_name)** — Search for types with producer/consumer/typedef info
10. **get_file_symbols(file_path)** — All symbols in a file

### Analysis (2 tools)
11. **search(name_substring)** — Search both symbols and types at once
12. **trace_data_flow(from, to, algorithm, max_depth)** — Find paths using 6 algorithms
13. **summarize_entry_point(entry_id, max_hops, follow_relations)** — Understand entry point structure

---

## 7. Example Walkthrough

**Scenario:** Understand how the `authenticate()` function works in myproject/backend.

### Session 1: Setup
```
set_active_graph(project="myproject", graph="backend")
list_entry_points()
```
Output: entry point is `repo::src/main.py`

### Session 2: Find authenticate
```
find_symbol(name_substring="authenticate")
```
Output: found `backend::auth/login.py::authenticate` at line 42

### Session 3: See what authenticate calls
```
expand_node(node_id="backend::auth/login.py::authenticate")
```
Output: calls `database::query()`, `logging::log()`, `validation::check()`

### Session 4: Trace request flow through authenticate
```
summarize_entry_point(
  entry_point_id="repo::src/main.py",
  max_hops=4,
  follow_relations=["calls"]
)
```
Output: main → request_handler → authenticate → database

### Session 5: Find all paths from authenticate to database
```
trace_data_flow(
  from_node_id="backend::auth/login.py::authenticate",
  to_node_id="backend::db.py::query",
  algorithm="data_flow",
  max_depth=5
)
```
Output: direct call or indirect through helper functions?

---

## 8. Tips & Tricks

### Discovering Node IDs
- Start with `get_feature_summary()` to list all files
- Use `get_file_symbols(file_path)` to get all symbols in a file with their IDs
- Use `find_symbol()` or `find_type()` if you know partial names

### Dealing with Large Graphs
- Start with `summarize_entry_point(max_hops=2)` for overview
- Increase `max_hops` gradually (2 → 3 → 4)
- Use `algorithm="bidirectional_bfs"` for faster path-finding on large graphs

### Data Pipeline Codebases
- Use `follow_relations=["calls", "produces", "consumes"]` in summarize_entry_point
- Use `algorithm="data_flow"` in trace_data_flow (prioritizes produces/consumes edges)

### Cross-File Understanding
- Look for `cross_file: true` in summarize_entry_point output
- File boundaries often reveal architectural layers

### Filtering Noise
- Use `--no-stdlib-calls` when building graphs for TS/JS to remove stdlib edges
- Use `--files` to focus on subset of codebase

---

## 9. Output Files

After running `run.py`, you'll find:

| File | Purpose |
|------|---------|
| `toc.json` | Table of contents (entry points, tier files, timestamps) |
| `tier_symbol.json` | Symbols, types, all edges (most queries use this) |
| `tier_file.json` | Files, directories, file-level edges |
| `feature_NAME.json` | Raw full graph before tiering (for debugging) |
| `viewer_NAME.html` | Standalone interactive D3 viewer (if < 1000 nodes) |

For MCP queries, only the tier files matter. The raw `feature_NAME.json` and viewer are optional.

---

## 10. Troubleshooting

| Problem | Solution |
|---------|----------|
| "No graph selected" | Call `set_active_graph(project="...", graph="...")` first |
| "Node not found" | Use `find_symbol()` or `get_feature_summary()` to find the correct node ID |
| "No file found" | Use `get_feature_summary()` to list all files and copy the exact path |
| Slow queries on large graph | Use `bidirectional_bfs` or `dijkstra` instead of `bfs`; increase `max_depth` incrementally |
| MCP server not connecting | Check that `codegrapher-mcp --graphs PATH` is running; verify PATH exists and contains toc.json files |

