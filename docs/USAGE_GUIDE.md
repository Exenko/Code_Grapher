# CodeGrapher Usage Guide

A practical guide for building graphs, exploring them in the browser, and optionally connecting an LLM via MCP.

---

## 1. Building a Graph

### Basic Command

```bash
codegrapher --feature myfeature --root /path/to/project --dir src
```

This parses `src/` (and all subdirectories) and writes output to `./graphs/myfeature/`.

### Output Directory

By default graphs go to `./graphs/` in your working directory. Use `--output-dir` to write somewhere else:

```bash
codegrapher --feature myfeature --root /path/to/project --dir src --output-dir /my/graphs/myproject/myfeature
```

### Multiple Input Patterns

```bash
codegrapher --feature myapp --root /path/to/project --files "src/**/*.py" "tests/test_*.py" --dir docs
```

### Command Cheat Sheet

| Goal | Flag |
| --- | --- |
| Single directory | `--dir src` |
| Multiple directories | `--dir src tests lib` |
| Glob patterns | `--files "src/*.py" "tests/test_*.py"` |
| Whole project | `--dir .` |
| Suppress stdlib noise | `--no-stdlib-calls` |

---

## 2. Exploring in the Browser

```bash
codegrapher-serve --graphs ./graphs
# or point at any directory containing graphs:
codegrapher-serve --graphs /my/graphs --port 8080
```

Opens at `http://localhost:5000`.

### Navigation

The viewer has four tiers — each loads on demand so large codebases stay fast:

1. **Repo tier** — top-level view of all directories
2. **Directory tier** — files within a directory and their relationships
3. **File tier** — all symbols in a file
4. **Symbol tier** — individual functions/classes with all incoming and outgoing edges

Click any node to expand it to the next tier. Click the node detail panel for edge breakdowns, state diagrams (call flow), and type diagrams.

### Controls

- **Search bar** — highlights matching nodes, dims the rest, auto-zooms on a single match
- **Edge-type filters** — show/hide calls, modifies, uses_type, maps_to, etc.
- **Zoom slider** — up to 500%; use for dense symbol graphs
- **State Diagram button** — renders the call-flow diagram for the selected entry point
- **Type Diagram button** — renders the type expansion diagram for the selected type node

### Tips

- Use `--no-stdlib-calls` when parsing TypeScript/JS to remove noisy stdlib edges
- For projects over ~1000 nodes the standalone HTML is not generated — use `codegrapher-serve` instead
- The `graphs/` directory is self-contained; copy it anywhere and re-serve

---

## 3. Output Files

| File | Purpose |
| --- | --- |
| `toc.json` | Table of contents — entry points, tier file paths, timestamps |
| `tier_symbol.json` | Symbols, types, all edges (most queries use this) |
| `tier_file.json` | Files, directories, file-level edges |
| `viewer_NAME.html` | Standalone viewer baked with graph data (if < 1000 nodes) |

---

## 4. MCP Server (LLM Integration)

If you want an LLM (Claude, etc.) to navigate the graph programmatically, start the MCP server:

```bash
codegrapher-mcp --graphs ./graphs
```

### Connect from Claude Desktop

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "codegrapher": {
      "command": "codegrapher-mcp",
      "args": ["--graphs", "/path/to/graphs"]
    }
  }
}
```

### Connect from Claude Code

```bash
claude mcp add --scope user --transport stdio codegrapher -- codegrapher-mcp --graphs /path/to/graphs
```

### Available MCP Tools (13)

#### Graph Navigation

- `list_projects()` — all available projects
- `list_graphs(project)` — all graphs in a project
- `set_active_graph(project, graph)` — select a graph for the session
- `get_active_graph()` — check which graph is active

#### Overview

- `list_entry_points()` — entry point list
- `get_feature_summary()` — node counts, files, edge counts, languages

#### Search

- `expand_node(node_id)` — node and all its edges
- `find_symbol(name_substring)` — search symbols by name
- `find_type(type_name)` — search types with producer/consumer/typedef info
- `get_file_symbols(file_path)` — all symbols in a file
- `search(name_substring)` — search symbols and types together

#### Analysis

- `trace_data_flow(from, to, algorithm, max_depth)` — find paths using 6 algorithms
- `summarize_entry_point(entry_id, max_hops, follow_relations)` — understand entry point structure

---

## 5. Troubleshooting

| Problem | Solution |
| --- | --- |
| No graphs listed in viewer | Check that `--graphs` points to the directory containing the graph subdirectories, not into a specific graph |
| Diagram panel shows render error | Copy the raw source shown and paste into [mermaid.live](https://mermaid.live) to debug; very large graphs may exceed renderer limits |
| Slow viewer on large graph | Start at repo or directory tier, drill down rather than loading symbol tier directly |
| MCP "no graph selected" | Call `set_active_graph(project="...", graph="...")` first |
| MCP "node not found" | Use `find_symbol()` or `get_feature_summary()` to find the correct node ID format |
