# CodeGrapher

AST-based codebase cartography tool. Point it at any project and it parses your source files into an interactive graph of files, symbols, and relationships — then serves them in a D3 force-directed viewer with level-of-detail loading.

**Supported languages:** Python, C/C++, TypeScript/JavaScript, Java, Kotlin, Protobuf, XML/WSDL

---

## Install

```bash
pip install git+https://github.com/Exenko/Code_Grapher.git
```

Requires Python 3.10+.

---

## Quick start (human viewer)

```bash
# 1. Parse your project into a graph (writes to ./graphs/project/myapp/)
codegrapher --feature myapp --root /path/to/project --dir src

# 2. Open the interactive viewer
codegrapher-serve --graphs ./graphs/project/myapp
```

The viewer opens at `http://localhost:5000`. Navigate from repo → directories → files → symbols using the force-directed graph. Click any node to expand it, use the search bar to find symbols, and use the edge-type filters to focus on calls, types, or data flow.

For large graphs, start at the repo or directory tier and drill down — the viewer loads each level on demand so it stays fast.

---

## Commands

### `codegrapher` — parse a codebase into a graph

```text
codegrapher --feature NAME --root PATH --dir SUBDIR [options]
```

| Argument | Description |
| --- | --- |
| `--feature NAME` | Label for this graph (used in output filenames) |
| `--root PATH` | Root directory of the project to parse |
| `--dir SUBDIR` | Subdirectory to scan, relative to `--root`. Use `.` for the whole project |
| `--files GLOB ...` | File glob patterns instead of (or in addition to) `--dir` |
| `--no-stdlib-calls` | Suppress edges to stdlib/built-in symbols (Python, TS/JS) |
| `--standalone` | Bake the graph into a self-contained HTML file (auto: on if <1000 nodes) |

Output goes to `./graphs/<project>/<feature>/` by default, where `<project>` is the name of the directory passed to `--root`. Use `--output-dir PATH` to write to a custom location instead.

**Examples:**

```bash
# Whole project
codegrapher --feature myapp --root . --dir .

# Specific subdirectory
codegrapher --feature backend --root /path/to/project --dir src/backend

# Filter out noisy stdlib calls
codegrapher --feature frontend --root . --dir src --no-stdlib-calls
```

---

### `codegrapher-serve` — interactive web viewer

```text
codegrapher-serve --graphs PATH [--port PORT]
```

Serves the graph viewer with progressive level-of-detail loading.

```bash
codegrapher-serve --graphs ./graphs
codegrapher-serve --graphs /path/to/graphs --port 8080
```

**Viewer features:**

- Force-directed D3 graph with zoom/pan
- Level-of-detail tiers: repo → directory → file → symbol
- Click any node to see its edges and details
- Search bar to highlight matching nodes
- Edge-type filter buttons (calls, modifies, uses_type, etc.)
- State diagram and type diagram panels for selected nodes
- Zoom up to 500% for dense graphs

---

### `codegrapher-mcp` — MCP server for LLM integration

```text
codegrapher-mcp --graphs PATH
```

Starts a [Model Context Protocol](https://modelcontextprotocol.io) server exposing 13 tools for LLM-assisted codebase exploration. `PATH` is the **graphs root** — a directory whose subdirectories are named projects, each containing named graph subdirectories.

The default output layout (`codegrapher --feature myapp --root . --dir .` with no `--output-dir`) already matches this structure: graphs land in `./graphs/<project>/<feature>/`, so `--graphs ./graphs` works out of the box.

See [docs/USAGE_GUIDE.md](docs/USAGE_GUIDE.md) for Claude Code and Claude Desktop setup.

> **Note:** The MCP server uses process-level global state for the active graph. Running two concurrent Claude sessions against the same `codegrapher-mcp` process will cause them to interfere. Start a separate server process per session if you need concurrent access.

---

## Typical workflow

```bash
cd /path/to/your/project

# Parse (writes to ./graphs/your-project/myapp/)
codegrapher --feature myapp --root . --dir .

# Explore in browser
codegrapher-serve --graphs ./graphs/your-project/myapp
```

The `graphs/` directory is self-contained — you can copy it anywhere and re-run `codegrapher-serve` against it.

---

## Output files

After running `codegrapher`, the output directory contains:

| File | Purpose |
| --- | --- |
| `toc.json` | Table of contents — entry points, tier file paths, metadata |
| `tier_symbol.json` | All symbols, types, and edges (most detailed tier) |
| `tier_file.json` | Files, directories, file-level edges |
| `viewer_NAME.html` | Self-contained viewer baked with the graph data (if < 1000 nodes) |

---

## Known limitations

- **Python:** Unannotated dependency injection and untyped method chains are not resolved
- **C++:** Inherited methods from out-of-scope base classes and deep `->` dereference chains are not resolved
- **TypeScript/JS:** Chained property calls through destructuring and external package symbols are not resolved
- These are fundamental AST limitations — everything that can be statically resolved without a full type system is resolved
