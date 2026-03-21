# CodeGrapher — LOD Server Architecture Handoff

> Written at session end. Next session should start here.
> Context at time of writing: ~64% used.

---

## What this feature is

Replace the current "bake everything into one giant HTML" approach with a proper
client-server architecture using Level of Detail (LOD) — like video game render
distance. Only load graph data that is currently in view, at the detail level
appropriate to the current zoom level.

**Three problems solved simultaneously:**
1. Render performance — D3 breaks above ~2,000 nodes. 3,500 already strains it.
2. Token efficiency — AI agents should load only the slice they need, not 194KB.
3. Cognitive load — humans need progressive disclosure, not a 3,500-node hairball.

---

## Decisions already made

| Decision | Choice |
|----------|--------|
| Keep `--standalone` flag? | Yes — opt-in, default ON for <1000 nodes, OFF for large graphs |
| Node index file? | No — derive owning file from node ID format (already self-describing) |
| Server framework | stdlib `http.server` preferred, Flask acceptable if needed |
| Spatial positions | Baked into tier JSONs at build time (deterministic, not physics) |

---

## Node ID format (self-describing, no index needed)

```
autofill::Client_Side/utils/autofill_engine.py::score_recipe_for_session
feature  :: rel/path/to/file.py                :: symbol_name

autofill::dir::Client_Side/utils
feature  :: dir :: rel/dir/path

autofill::repo::repo
```

The server parses node IDs to find which file owns a node — no separate index.

---

## New files to create (agreed in advance)

| File | Purpose |
|------|---------|
| `CodeGrapher/serve.py` | Local HTTP server — static files + `/api/neighbors` endpoint |

That is the ONLY new file. Everything else is modifications to existing files.

---

## Files to modify

| File | What changes |
|------|-------------|
| `CodeGrapher/run.py` | Add `--standalone` flag; default behavior generates JSON only (no HTML) for large graphs |
| `CodeGrapher/tiered_builder.py` | Add spatial position hints (`x`, `y`) to all tier nodes at build time |
| `CodeGrapher/viewer/index.html` | Remove GRAPH_DATA sentinel; add fetch-on-load bootstrap |
| `CodeGrapher/viewer/graph.js` | Replace `init(GRAPH_DATA)` with fetch lifecycle + zoom-triggered LOD loading |

---

## serve.py — full spec

### Startup
```
py CodeGrapher/serve.py --graphs CodeGrapher/graphs --port 5000
```
Opens browser automatically to `http://localhost:5000`.

### Endpoints

| Endpoint | Response |
|----------|----------|
| `GET /` | Serves `viewer/index.html` |
| `GET /viewer/<file>` | Serves static viewer assets (graph.js, styles.css, d3.min.js) |
| `GET /graphs/<path>` | Serves any file under graphs/ directory (toc.json, tier_*.json, sub/*.json) |
| `GET /api/neighbors?id=<node_id>` | Returns immediate neighbors of a node from the appropriate tier file |

### `/api/neighbors` logic
1. Parse the node ID to determine which sub-graph file owns it
   - If ID contains `::dir::` → look in `tier_directory.json`
   - If ID contains `::repo::` → look in `tier_repo.json`
   - If ID has two `::` separators (file node) → look in `tier_file.json`
   - If ID has three `::` separators (symbol node) → parse the file path component,
     find the matching entry point slug in `toc.json`, load `sub/main_<slug>.json`
2. Find the node in that file
3. Return all edges where `from == node_id` or `to == node_id`, plus the neighbor nodes
4. Response shape:
```json
{
  "node": { ...node dict... },
  "neighbors": [ ...node dicts... ],
  "edges": [ ...edge dicts... ]
}
```

### Server implementation preference
Use stdlib `http.server.BaseHTTPRequestHandler` — no dependencies.
Flask only if the routing logic becomes too painful in raw stdlib.

---

## tiered_builder.py — spatial position additions

Each node in each tier file needs `x` and `y` fields baked in at build time.

### Layout algorithm (deterministic, no physics)

**tier_directory.json:**
- Sort directories by path depth, then alphabetically
- Arrange in a grid: ~sqrt(N) columns
- Each directory node gets `x = col * 250, y = row * 200`

**tier_file.json:**
- Files cluster around their parent directory's position
- Within each directory cluster: arrange files in a circle of radius 100
  around the directory's `x, y` position
- Formula: `x = dir_x + 100 * cos(i * 2π / n)`, `y = dir_y + 100 * sin(i * 2π / n)`

**sub/main_*.json:**
- Symbols cluster around their file node position
- Same radial formula, smaller radius (60px)
- Methods cluster tighter around their class node (radius 30px)

These are **hints**, not locks. The viewer passes them as D3's `node.x` and `node.y`
initial positions (not `fx`/`fy`), so the simulation can still adjust them.
This means the graph settles quickly instead of exploding from random positions.

---

## graph.js — LOD loading lifecycle

### State machine

```
IDLE
  → on load: fetch toc.json + tier_directory.json → render dir nodes → DIR_ONLY

DIR_ONLY  (zoom < 0.5)
  → on zoom in past 0.5: fetch tier_file.json → merge file nodes → FILE_LEVEL
  → on click dir node: fetch /api/neighbors → expand that dir's files inline

FILE_LEVEL  (0.5 ≤ zoom < 1.5)
  → on zoom in past 1.5 on a cluster: fetch sub/main_*.json for visible files → SYMBOL_LEVEL
  → on zoom out past 0.5: hide file nodes, show only dir nodes → DIR_ONLY

SYMBOL_LEVEL  (zoom ≥ 1.5)
  → on zoom out: collapse symbols back to file nodes → FILE_LEVEL
  → "Flowchart from here" button: BFS + layered layout (already implemented)
```

### Viewport-based loading ("render distance")

When transitioning to SYMBOL_LEVEL, only load sub-graphs for files whose
position falls within the current viewport + a 20% buffer zone.

```javascript
function getViewportNodeIds(transform, width, height, nodes) {
  const x0 = -transform.x / transform.k - width * 0.2;
  const x1 = (width - transform.x) / transform.k + width * 0.2;
  const y0 = -transform.y / transform.k - height * 0.2;
  const y1 = (height - transform.y) / transform.k + height * 0.2;
  return nodes
    .filter(n => n.type === 'file' && n.x >= x0 && n.x <= x1 && n.y >= y0 && n.y <= y1)
    .map(n => n.id);
}
```

### Graph merging (additive, never replaces)

When new data arrives from a fetch, merge it into the live graph without
resetting the simulation. D3's simulation supports live node/link additions.

```javascript
// Pattern: add new nodes/links, reheat simulation gently
simulation.nodes([...existingNodes, ...newNodes]);
simulation.force("link").links([...existingLinks, ...newLinks]);
simulation.alpha(0.1).restart();  // gentle reheat, not full restart
```

Nodes already in the graph are never duplicated — check by ID before merging.

### LOD display rules (CSS class toggling, not data removal)

| Zoom level | Visible node types | Hidden node types |
|------------|-------------------|------------------|
| < 0.5 | directory, repo | file, symbol, type |
| 0.5–1.5 | directory, file | symbol, type |
| > 1.5 | all loaded | none |

Use `nodeSel.style("display", ...)` based on zoom + node type.
Never unload nodes from memory once loaded — only hide them visually.

---

## run.py — `--standalone` flag spec

```
py CodeGrapher/run.py --feature autofill --root . --files "..." --standalone
py CodeGrapher/run.py --feature repo --root . --dir Client_Side  # no --standalone → JSON only
```

Logic:
```python
# Auto-detect if not specified
if args.standalone is None:
    args.standalone = feature_graph.node_count() < 1000

if args.standalone:
    _build_standalone_viewer(...)  # existing behavior
    print(f"Standalone viewer -> {viewer_out}")
else:
    print(f"Run: py CodeGrapher/serve.py --graphs {graphs_dir}")
    print(f"Then open: http://localhost:5000")
```

---

## Implementation order for next session

Do these in order — each step is independently testable:

1. **`tiered_builder.py` spatial positions** — add `x`/`y` to all tier nodes.
   Test: run on repo, check that tier_directory.json nodes have x/y fields.

2. **`serve.py`** — static file server + `/api/neighbors` endpoint.
   Test: `py serve.py`, open browser, check that `http://localhost:5000/graphs/toc.json` serves correctly.

3. **`viewer/index.html`** — remove GRAPH_DATA sentinel, add loading spinner,
   fetch `toc.json` on load, then fetch `tier_directory.json`.
   Test: open via serve.py, confirm directory nodes appear.

4. **`graph.js`** — LOD state machine, zoom triggers, viewport-based loading.
   Test: zoom in on a directory cluster, confirm file nodes appear.
   Test: zoom in further, confirm symbol nodes appear for visible files only.

5. **`run.py`** — `--standalone` flag, auto-detect threshold.
   Test: run with <1000 node feature → HTML generated. Run repo → JSON only + server instructions.

---

## Current working state (before this feature)

The tool works end-to-end right now with standalone HTML output:
```
py CodeGrapher/run.py --feature repo --root . --dir Client_Side Server_Side test_scripts
```
Outputs: `graphs/viewer_repo.html` (754KB, 3508 nodes, works but slow)
Also outputs: `graphs/tier_*.json`, `graphs/sub/*.json`, `graphs/toc.json`

The tier JSON files already exist and are correctly structured.
The `tiered_builder.py` just needs spatial positions added to them.

---

## Files NOT to touch

- `CodeGrapher/schema.py` — complete, no changes needed for this feature
- `CodeGrapher/graph.py` — complete, no changes needed
- `CodeGrapher/parser_python.py` — complete, no changes needed
- `CodeGrapher/viewer/styles.css` — may need minor additions for loading states
- `CodeGrapher/viewer/d3.min.js` — never touch

---

## Key constraint reminder

**Do not create any files not listed in the "new files" section above.**
The only new file is `serve.py`. Everything else is modifications.
