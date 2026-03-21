# CodeGrapher — Phase 2 Specification

> Decisions recorded from design session. This is the implementation contract.
> Do not implement anything not described here without updating this doc first.

---

## What Phase 1 delivered (baseline)

- Python AST parser (`parser_python.py`) — 2-pass, extracts imports/defines/calls/uses_type/contains
- Graph object (`graph.py`) — dedup, merge, serialize
- Schema (`schema.py`) — Node/Edge dataclasses, ID factories
- CLI (`run.py`) — `--feature`, `--root`, `--files` (glob patterns), emits JSON + standalone HTML viewer
- Viewer (`viewer/`) — D3 v7 force-directed, click/search/sidebar/filter

Phase 1 output: one flat feature graph (419 nodes, 1734 edges for autofill).

---

## Phase 2 Goals

Three independent capabilities, each buildable without the others:

### 1. Directory input (`--dir`)

Add `--dir <path>` flag to `run.py` alongside the existing `--files`.
Expands to all `.py` files under that directory recursively.
Can be combined with `--files` in the same invocation.
No schema changes required — purely a CLI addition to `run.py`.

### 2. Trace-from-entry-point (viewer feature)

Given a root node (a "main" or any file/symbol), do a BFS traversal of the
graph following directed edges, and render only the reachable subgraph.

This is a **viewer-side feature** — no parser or schema changes.
The full graph JSON already contains all the data needed.
The viewer adds a "Trace from here" button in the node sidebar that triggers
the BFS filter mode. A "Show all" button resets to the full graph.

Edges to follow in BFS (directed, outward):
- `calls` — most important for tracing execution flow
- `imports` — to show what a file pulls in
- `defines` / `contains` — to include symbols owned by a file/class

Edge directionality matters: BFS follows edges **from** the selected node
outward, not inward. This shows "what does X touch?" not "what touches X?".

### 3. Hierarchical / tiered graph model

The core Phase 2 architectural feature.

---

## Tiered Graph Model

### Mental model

Like a table of contents: the depth of the TOC scales with the size of the
codebase. A small project might have 3 tiers; a large monorepo might have 6.
Tier count is an **output** of analysis, not a fixed parameter.

Progressive disclosure: start at the top, expand only what you need.
Designed for three consumers equally: humans, rendering engines, AI agents.

### Primary structure: filesystem hierarchy

The directory tree provides the skeleton. Import/call edges provide the
connective tissue within and across tiers.

| Tier name | Node represents | Typical count |
|-----------|----------------|---------------|
| repo | Repository root | 1–5 |
| directory | Directory / package | 10–100 |
| file | Single `.py` file | 100–10,000 |
| symbol | Function / class | 1,000–1,000,000 |

The tier count is determined by how many directory levels exist between the
repo root and the leaf files. Shallow projects collapse naturally.

### "Main" detection (entry point discovery)

A "main" is the primary public surface of a unit of code. Detected in order:

1. Has `if __name__ == "__main__":` → definite script entry point
2. Is an `__init__.py` → package surface (library entry point)
3. Has zero incoming `imports` edges from within the parsed scope → graph root
4. Explicitly listed via `--entry-points` flag (user override)

Detection runs after Pass 1 (full import graph is known before Pass 2).

### JSON output structure

```
graphs/
  sub/
    main_<slug>.json       ← one per detected entry point
  tier_symbol.json         ← full flat graph (current Phase 1 output, renamed)
  tier_file.json           ← one node per file, edges summarized
  tier_directory.json      ← one node per directory, edges summarized
  tier_repo.json           ← top level (may be trivial for single-repo projects)
  toc.json                 ← index of everything that exists
```

**Sub-graphs (`sub/main_<slug>.json`) are referential, not inclusive.**
A sub-graph for `autofill_engine.py` includes its own symbols fully.
Files it imports from other entry-point territories appear as **stub nodes**
with a `ref` field pointing to `sub/main_<slug>.json` for that file.
No symbol-level data is duplicated across sub-graph files.

### Edge promotion (cross-tier summarization)

A `calls` edge between two symbols in different directories produces:
- A `calls` edge in `tier_symbol.json` (full detail)
- A summarized `depends_on` edge in `tier_file.json` (file → file)
- A summarized `depends_on` edge in `tier_directory.json` (dir → dir, with count)

The summarized edge carries a `count` field: how many lower-tier edges it
represents. Example: `Client_Side/utils/ → Server_Side/api/  (14 calls)`.

Cross-tier edges stay **visible at all tiers** — they do not disappear when
you zoom out. They become summarized arrows with counts.

### `toc.json` format

```json
{
  "generated": "2026-03-07T...",
  "tiers": ["repo", "directory", "file", "symbol"],
  "entry_points": [
    {
      "slug": "main_client",
      "file": "Client_Side/main.py",
      "reason": "has __main__ block",
      "graph": "sub/main_client.json"
    }
  ],
  "tier_files": {
    "symbol": "tier_symbol.json",
    "file": "tier_file.json",
    "directory": "tier_directory.json",
    "repo": "tier_repo.json"
  }
}
```

---

## Schema additions required

New node types needed for tiered graphs:

```python
class NodeType(str, Enum):
    FILE = "file"
    SYMBOL = "symbol"
    TYPE = "type"
    DIRECTORY = "directory"   # NEW — Phase 2
    REPO = "repo"             # NEW — Phase 2
```

New edge relations needed:

```python
class EdgeRelation(str, Enum):
    # existing
    DEFINES = "defines"
    IMPORTS = "imports"
    CALLS = "calls"
    USES_TYPE = "uses_type"
    CONTAINS = "contains"
    # new
    DEPENDS_ON = "depends_on"   # summarized cross-file/cross-dir edge
    ENTRY_OF = "entry_of"       # entry-point file → its directory
```

New Node fields needed:

```python
@dataclass
class Node:
    # existing fields ...
    ref: Optional[str] = None        # for stub nodes: path to the sub-graph JSON
    count: Optional[int] = None      # for summary nodes: how many lower-tier items
```

New Edge fields needed:

```python
@dataclass
class Edge:
    # existing fields ...
    count: Optional[int] = None      # for promoted edges: how many lower-tier edges
```

---

## New files to be created

Only two new Python files are needed. Both agreed in advance:

| File | Purpose |
|------|---------|
| `CodeGrapher/tiered_builder.py` | Reads a flat feature graph, detects entry points, emits all tier JSONs and sub-graphs |
| `CodeGrapher/stitch.py` | (later) Merges multiple feature graphs across the full repo |

`run.py` is modified (not replaced) to:
1. Accept `--dir` in addition to `--files`
2. After emitting the flat graph, call `tiered_builder.py` to produce tier files

`viewer/graph.js` is modified to:
1. Add "Trace from here" BFS filter button in the node sidebar
2. Add "Show all" reset button

---

## Implementation order

1. `--dir` flag in `run.py` — smallest change, validates the pipeline still works
2. Schema additions (DIRECTORY, REPO node types; DEPENDS_ON, ENTRY_OF edges; ref/count fields)
3. Entry point detection logic (can be a function in `tiered_builder.py`)
4. `tiered_builder.py` — tier file generation + sub-graph emission
5. `toc.json` generation
6. Viewer BFS trace feature

Items 1 and 6 are independent of each other and of items 2–5.
Items 2–5 must be done in order.

---

## Constraints

- No new files beyond those listed in the "New files" table above
- Sub-graphs are referential (not inclusive) by default
  - `--inclusive` flag may be added later as opt-in
- Tier count is derived from filesystem depth, not hardcoded
- The existing `feature_<name>.json` output is preserved (renamed to `tier_symbol.json` in the new structure, but the old path still written for backward compat)
- All new code must work on Windows (forward-slash paths, cp1252-safe console output)
