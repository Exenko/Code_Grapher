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

## Quick start

```bash
# 1. Generate the graph (run from your project root, or use absolute paths)
codegrapher --feature myapp --root . --dir .

# 2. Open the viewer
codegrapher-serve --graphs ./graphs
```

The viewer opens automatically in your browser at `http://localhost:5000`.

---

## Commands

### `codegrapher` — parse a codebase into a graph

```
codegrapher --feature NAME --root PATH --dir SUBDIR [options]
```

| Argument | Description |
|---|---|
| `--feature NAME` | Label for this graph (used in output filenames) |
| `--root PATH` | Root directory of the project to parse |
| `--dir SUBDIR` | Subdirectory to scan, relative to `--root`. Use `.` for the whole project |
| `--files GLOB ...` | File glob patterns instead of (or in addition to) `--dir` |
| `--no-stdlib-calls` | Suppress edges to stdlib/built-in symbols (Python, TS/JS) |
| `--standalone` | Bake the graph into a self-contained HTML file (auto: on if <1000 nodes) |

Output goes to `./graphs/` in the current working directory.

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

```
codegrapher-serve --graphs PATH [--port PORT]
```

Serves the graph viewer with progressive level-of-detail loading. Navigate from repo → directories → files → symbols without loading the entire graph at once.

```bash
codegrapher-serve --graphs ./graphs
codegrapher-serve --graphs /path/to/project/graphs --port 8080
```

---

### `codegrapher-mcp` — MCP server for LLM integration

```
codegrapher-mcp --graphs PATH
```

Starts a [Model Context Protocol](https://modelcontextprotocol.io) server exposing 9 tools for LLM-assisted codebase exploration. Connect any MCP-compatible client (Claude Desktop, Claude Code, etc.) to let an LLM navigate the graph.

**Available tools:** `get_overview`, `expand_node`, `find_type`, `find_symbol`, `get_file_symbols`, `search`, `summarize_entry_point`, `trace_data_flow`, `follow_relations`

```bash
# Generate graphs first, then start the MCP server
codegrapher --feature myapp --root . --dir .
codegrapher-mcp --graphs ./graphs
```

---

## Typical workflow

```bash
cd /path/to/your/project

# Parse
codegrapher --feature myapp --root . --dir .

# Explore in browser
codegrapher-serve --graphs ./graphs

# (Optional) Connect an LLM via MCP
codegrapher-mcp --graphs ./graphs
```

The `graphs/` directory is self-contained — you can copy it anywhere and re-run `codegrapher-serve` against it.

---

## Known limitations

- **Python:** Unannotated dependency injection and untyped method chains are not resolved (requires type inference beyond AST)
- **C++:** Inherited methods from out-of-scope base classes and deep `->` dereference chains are not resolved
- **TypeScript/JS:** Chained property calls through destructuring and external package symbols are not resolved
- These are fundamental AST limitations, not bugs — everything that can be statically resolved without a full type system is resolved
