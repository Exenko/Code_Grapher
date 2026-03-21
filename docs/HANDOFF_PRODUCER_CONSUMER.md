# CodeGrapher — Producer/Consumer + LOD Viewer Handoff

> Written at session end. Next session should start here.
> HANDOFF_LOD_SERVER.md is stale — LOD server is fully implemented. This file supersedes it.

---

## What was built (session 1)

### 1. Producer/Consumer data flow model (design + implementation)

Full design documented in `design.md` under "Producer / Consumer Model" section.

**New edge relations in `schema.py`:**
- `PRODUCES` — symbol emits a value of this type (return or param mutation)
- `CONSUMES` — symbol takes a value of this type as input
- `TYPEDEF_OF` — intra-language type alias (stub, not yet emitted by any parser)

**New edge metadata fields in `schema.py` `Edge` dataclass:**
- `via: Optional[str]` — `"return_value"` or `"param_mutation"`
- `relay: Optional[bool]` — True if symbol received value from upstream and forwarded it
- `role: Optional[str]` — `"data"` or `"control"` (control = shapes behavior, data doesn't appear in output)
- `ptr_depth: Optional[int]` — pointer dereference depth for `contains` edges (0=direct, 1=*, 2=**)
- `seq: Optional[int]` — relative call order within a function body

**`parser_python.py` — what it now emits:**
- `produces(via:return_value)` from return type annotations
- `produces(via:return_value, relay:True)` when signature analysis OR body `return param_name` confirms relay
- `consumes(role:data)` from parameter annotations (non-mutable, non-config types)
- `consumes(role:control)` when type name matches Config/Settings/Options/Params/Cfg/etc heuristic
- `produces(via:param_mutation)` for annotated mutable containers (`dict`, `list`, etc.)
- `produces(via:param_mutation, unresolved:True)` for unannotated params mutated in body (attribute assignment or mutating method calls)
- `seq` stamped on every `calls` edge — relative call order within the function body
- `uses_type` retained as fallback when direction cannot be determined

**Body walking (Tier 2 inference — AST, no execution):**
- `_walk_body()` walks statements in order, recurses into control flow blocks
- Detects `obj.field = x` and `obj.method(...)` for known mutating methods on params
- `_detect_relay_from_return()` scans `return` statements for bare param names

**Tiered inference model (design only, Tier 3+ not yet implemented):**
```
Tier 1: Signature analysis     — always available, no deps (done)
Tier 2: AST body walking       — always available, no deps (done)
Tier 3: mypy/pyright           — optional, requires working env (deferred)
Tier 4: Compiler IR (clangd)   — C++ only, requires build system (deferred)
```
All tiers emit identical schema fields — the source of inference is an implementation detail.

### 2. Verified output

Running:
```
py CodeGrapher/run.py --feature repo --root . --dir Client_Side Server_Side test_scripts
```

Produces in `CodeGrapher/graphs/`:
- `tier_symbol.json` — 3,472 nodes, 15,822 edges
- `tier_file.json` — 375 nodes, 1,848 edges
- `tier_directory.json` — 22 nodes, 116 edges
- `tier_repo.json` — 23 nodes, 22 edges
- `toc.json` — 4 tiers, 199 entry points
- `sub/*.json` — 208 sub-graphs

Confirmed in output:
- 61 `produces` edges, 65 `consumes` edges
- 6 `relay:True` edges (body analysis confirmed, e.g. `autofill_engine::merge_meal_requirements`)
- 11,484 `calls` edges all have `seq` stamped
- `role:control` = 0 (SmartRecipeApp doesn't use Config/Settings naming heavily)

---

## What was built (session 2, 2026-03-08)

### 3. Viewer — three new features in `viewer/graph.js`

#### Feature A: Edge-relation filter toggles

A row of colored toggle buttons is injected into `#controls` at runtime by `setupRelationFilters()`.

- One button per relation type (all 10 from `RELATION_COLORS`)
- Clicking hides/shows all edges of that relation — state stored in `hiddenRelations` Set
- Composes with LOD visibility: `applyLodVisibility()` now checks `hiddenRelations.has(d.relation)` first
- Buttons go faded + strikethrough when relation is hidden

#### Feature B: Data flow trace (`applyDataFlowTrace(nodeId)`)

New function added after `resetTrace()`. Triggered by a new teal "Data flow trace" button in the sidebar (appears for type and symbol nodes only).

- Walks only `produces`, `consumes`, `calls`, `defines` edges (not all edges like BFS flowchart)
- Orders nodes by `seq` within each depth level, not alphabetically
- Depth capped at 3 to prevent blowup
- Edge labels show full metadata: `relation [seq] via:... relay control`
- Shares `resetTrace()` for the "Back to full graph" button

#### Feature C: Type structure sidebar panel

In `renderSidebar()`, when `node.type === "type"`, a monospace block is inserted showing all outgoing `contains` edges as a `TypeName { field* }` tree with pointer depth annotations.

---

## What was built (session 3, 2026-03-09)

### 4. Entry point detection fix (`tiered_builder.py`)

The previous Rule 3 ("zero incoming imports = entry point") was firing for nearly every file because cross-file import resolution is incomplete — most imports are unresolved and don't generate edges between files. This inflated entry points from a meaningful count to 199 out of 200 files.

**Changes made:**

- Eliminated Rule 3 entirely (zero incoming imports — unreliable due to unresolved cross-file imports)
- Tightened Rule 1: `if __name__ == "__main__"` files are only entry points if they don't match script/migration/setup path patterns (`/tests/`, `/test_scripts/`, `/scripts/`, `/first_boot/`, `/db/`, `/utils/`) or filename prefixes (`migrate_`, `populate_`, `rebuild_`, `setup_`, `create_`, `analyze_`, `repopulate_`, `fix_`, `sync_`, `consolidate_`, `derive_`, `validate_`, `batch_`, `export_`, `autocomplete_`)

**Result:** 199 entry points reduced to 24 — a meaningful set of real application entry points.

### 5. New `analyze/` directory — two static analysis modules

#### `analyze/flow_trace.py` — execution flow to Mermaid

Reads `tier_symbol.json`, traces execution from a named entry point, and emits a Mermaid `stateDiagram-v2` diagram.

Public interface:

```python
trace(graph_path, entry_file, output="mermaid", symbol_name=None) -> str
```

Key design decisions:

- Entry symbol resolution order: explicit `--symbol` arg > `main()` > `__init__` > first symbol by line number
- DFS walk following `calls` edges in `seq` order, max_depth=6
- Unresolved and stdlib nodes are filtered out
- Back-edge (cycle) detection: emits cycle steps rather than silently dropping
- Callback boundary detection: flags symbols whose names match `register`/`subscribe`/`on_`/`connect`/`bind`/`emit`/`dispatch` patterns
- Directory-relative labeling: strips the longest common path prefix so labels show meaningful relative paths (not full absolute-style IDs)
- Two output sections: FILE LEVEL (file-to-file flow) and SYMBOL LEVEL (function-to-function, grouped by file)
- Short stable state IDs: S0, S1, S2... per trace call

CLI:

```bash
py CodeGrapher/analyze/flow_trace.py --graph CodeGrapher/graphs/tier_symbol.json --entry Client_Side/main.py --symbol health_check
```

Integrated into `run.py` via `--analyze flow`.

#### `analyze/type_expander.py` — recursive type/struct tree

Recursively expands a named type following `contains` and `uses_type` edges.

Public interface:

```python
expand(graph_path, type_name, output="text") -> str
list_types(graph_path) -> list[str]
```

Key design decisions:

- Cycle detection: emits `<cycle: TypeName>` instead of looping
- `ptr_depth` annotations on fields (shown as `*`, `**`, etc.)
- Distinguishes custom types (recurse) from primitives (leaf)
- Two output formats: indented text tree and Mermaid `classDiagram`

CLI:

```bash
py CodeGrapher/analyze/type_expander.py --graph CodeGrapher/graphs/tier_symbol.json --type RecipeScore --format text
py CodeGrapher/analyze/type_expander.py --graph CodeGrapher/graphs/tier_symbol.json --list
```

CLI-only for now — not yet integrated into `run.py` (flow_trace is integrated; type_expander is not).

### 6. Parser symbol collision fix (`parser_python.py`)

`_resolve_call_target` and `_resolve_type` both previously used a flat lookup that could resolve common method names (e.g. `close`, `get`, `execute`) to wrong files when multiple files defined symbols with the same name.

**Fix:** Both functions now use priority-ordered resolution:

1. Same-file symbols (nid starts with `feature::rel_path::`)
2. Same-module symbols (`::module_name::` in nid)
3. Cross-file fallback (any match — last resort)

---

## Session 4 accomplishments

### Fix: Entry symbol selection in flow_trace.py
- `_find_entry_symbol()` rewritten — dropped `__init__` priority, now prefers module-level functions ranked by outgoing call count, then line number
- Signature updated to accept `calls_from` dict for call-count ranking
- Call site in `trace()` updated to pass `calls_from`
- Result: `autofill_engine.py` now correctly selects `run_autofill_pipeline` as entry (was `LeftoverBank.__init__`)

### Fix: --list flag in type_expander.py CLI
- `--type` changed from `required=True` to `required=False` so `--list` works standalone

### Feature: Dataclass field nodes in parser_python.py
- Added `visit_AnnAssign()` to `_FileVisitor` — fires only for class-level annotated assignments
- Creates a `symbol` node per field with label `ClassName.field_name`
- Emits `contains` edge: class type node → field node
- Emits `uses_type` edges for non-builtin type annotations
- Result: symbol count 380 → 551, contains 328 → 499, uses_type 0 → 8 (autofill feature)
- `CookingSession`, `MealAssignment`, and all other dataclasses now expand correctly in type_expander

### Feature: --analyze type integrated into run.py
- `--analyze` choices expanded to `["flow", "type"]`
- `--type` argument added (class/type name)
- `_run_type_analysis()` function added — mirrors `_run_flow_analysis()` pattern
- Outputs `graphs/type_<TypeName>.mmd` (Mermaid classDiagram)
- If `--type` omitted, lists all available types and exits

### Verification: Problem 5 (false cross-file edges) confirmed resolved
- The suspicious edge `identify_cooking_opportunities → autofill::autofill_engine::CookingOpportunity` is a `produces` edge (return type annotation), not a `calls` edge
- `_walk()` only follows `calls` edges — no false cross-file traversal occurs
- Type node IDs using module-path format (`feature::module::Class`) is intentional (shared bridge node design)
- Problem 5 is CLOSED

### Fix: Edge color rendering bug in graph.js (Problem 3)

- Root cause: `.attr("stroke", d => ... : null)` for non-control edges set inline stroke to null, suppressing CSS relation colors
- Fix: replaced `null` with `RELATION_COLORS[d.relation] || "#888"` in both the initial render (line ~541) and `mergeGraphData` re-render (line ~296)
- Both relay (dashed stroke) and control (violet color) edges now render correctly
- Problem 3 is CLOSED

### Fix: applyDataFlowTrace wiring verified (Problem 4)

- Code audit confirmed: function is correctly wired to sidebar click handler, nodeSel2/linkSel2 naming is consistent, resetTrace is defined
- No code changes needed — was already correct
- Problem 4 is CLOSED (browser verification still recommended but no bugs found)

### Feature: Annotation text on field nodes (New problem)

- `schema.py`: added `annotation: Optional[str] = None` field to Node dataclass and `to_dict()`
- `parser_python.py`: `visit_AnnAssign` now calls `ast.unparse(node.annotation)` to store the full annotation string (e.g. `"List[Tuple[str, str]]"`) on each field node
- `analyze/type_expander.py`:
  - Fixed stale return type annotation on `_collect_fields` (was `list[tuple[...]]`, now `list[dict]`)
  - Text renderer now shows `field: annotation` for primitive fields using `sym.get("annotation")`
  - Mermaid renderer now shows `+annotation field` for primitive fields
  - Result: `CookingSession` mermaid output now shows `+List[Tuple[str, str]] meals_covered` etc.

### Feature: Per-file lazy loading at SYMBOL_LEVEL (Problem 2)

- `tiered_builder.py`:
  - `build_tiers()` now generates sub-graphs for ALL .py files, not just entry points
  - `_build_toc()` now accepts `all_file_slugs: Dict[str, str]` and emits a `files` map in toc.json
  - `files` map: `{file_path -> {slug, graph}}` covering every file
  - Result: 30 per-file sub-graphs generated for autofill feature (was 0 when no entry points detected)
- `viewer/graph.js`:
  - `loadVisibleSubGraphs()` now checks `toc.files` map (new) before falling back to `toc.entry_points` (legacy)
  - Final fallback: if no per-file sub-graphs match visible files, loads `tier_symbol.json` once (tracked via `__tier_symbol__` slug)
  - Problem 2 is CLOSED

---

## Session 5 accomplishments (2026-03-11)

### Viewer: Manual LOD buttons replacing auto-LOD

Removed auto-LOD zoom triggering entirely. `onZoom` function deleted. Three LOD buttons injected into `#controls` at startup (`setupLodButtons()`):

- **Directories** — shows directory nodes only (instant)
- **Files** — fetches `tier_file.json` on first press, then instant
- **Symbols** — switches to symbol level, loads visible sub-graphs

Active button is highlighted. `_fittingZoom` guard and all debounce timer logic removed. Zoom/pan only moves the camera.

### Viewer: Data flow trace button on file nodes

`renderSidebar` now shows the "Data flow trace" button for `file` nodes in addition to `type` and `symbol` nodes.

### Viewer: Data flow trace seeding for type/file nodes

`applyDataFlowTrace` now expands seed nodes before BFS:

- `type` nodes: resolves all `contains` children and seeds BFS from all of them
- `file` nodes: resolves all `defines` children and seeds BFS from those
- `symbol` nodes: seeds directly (unchanged)

### Parser: Three call resolution bugs fixed in `parser_python.py`

**Bug 1 — `super()` self-loop:** `super().__init__()` was resolving to the current class's own `__init__` (same-file priority), producing a spurious self-edge. Fix: `_is_super_call()` helper detects `super().*` calls in `_handle_call` and drops them before resolution.

**Bug 2 — Bare imported names resolving to same-file methods:** A bare call `get_theme_manager()` was resolving to `MainWindow.get_theme_manager()` (same-file method) instead of the imported module-level function. Fix: `visit_ImportFrom` now populates `self._import_names` (a `Set[str]`). In `_handle_call`, if the call name is in `_import_names`, `skip_same_file=True`.

**Bug 3 — Chained attr calls resolving to same-file methods:** `self._theme_manager.set_theme()` was resolving to `MainWindow.set_theme()`. Fix: `_extract_call_receiver` now returns `(root_name, chain_depth)`. When `chain_depth >= 2`, `skip_same_file=True`. When `skip_same_file=True`, the last-resort same-file fallback in `_resolve_call_target` is suppressed — returning None (unresolved) is more correct than returning the wrong same-file symbol.

**Bug 4 — Cross-file suffix match pollution:** Common method names like `run()` were matching `IngredientConsolidator.run()` in unrelated files via `label.endswith(".run")`. Fix: cross-file (`any_match`) bucket now only accepts exact label matches (`label == name`), never suffix matches. Suffix matching is only reliable within same-file or same-module context.

### Verification

Flow trace for `Client_Side/ui_new/main_window.py` now produces:

- `get_theme_manager() [theme_manager.py]` (was `MainWindow.get_theme_manager`)
- No self-loop on `__init__`
- `MainWindow.set_theme()` false positive gone
- `consolidate_ingredient_taxonomy.py` false cross-file pull in `main.py` trace gone

Remaining unresolved (expected — requires Tier 3 type inference):

- `self._theme_manager.on_theme_changed()` → unresolved (receiver type unknown without mypy)
- `self._theme_manager.set_theme()` → unresolved (same reason)
- `self._header.update_theme_indicator()` → unresolved (same reason)

---

## Outstanding problems

- **Tier 3 type inference (deferred):** `self.<attr>.method()` calls remain unresolved when the attr's type cannot be determined from a constructor call in `__init__`. Example: `self._theme_manager.on_theme_changed()` is unresolved because the parser doesn't track that `self._theme_manager = get_theme_manager()` returns a `ThemeManager`. This requires mypy/pyright integration (Tier 3) and is intentionally deferred.
- **Browser smoke test (Problem 4 partial):** `applyDataFlowTrace` wiring verified in code but not fully tested in a running browser end-to-end.

---

## How to run

```bash
# Build graphs
py CodeGrapher/run.py --feature repo --root . --dir Client_Side Server_Side test_scripts

# Serve with LOD server
py CodeGrapher/serve.py --graphs CodeGrapher/graphs
# opens http://localhost:5000

# Flow trace (from run.py)
py CodeGrapher/run.py --feature repo --root . --dir Client_Side --analyze flow --entry Client_Side/main.py

# Flow trace (direct, with specific symbol)
py CodeGrapher/analyze/flow_trace.py --graph CodeGrapher/graphs/tier_symbol.json --entry Server_Side/api/app.py --symbol health_check

# Type expansion
py CodeGrapher/analyze/type_expander.py --graph CodeGrapher/graphs/tier_symbol.json --type RecipeScore
py CodeGrapher/analyze/type_expander.py --graph CodeGrapher/graphs/tier_symbol.json --list
```

---

## Key files

| File | Status | Notes |
|------|--------|-------|
| `schema.py` | Done | All new fields live here |
| `parser_python.py` | Fixed | Priority-ordered symbol resolution (session 3) |
| `tiered_builder.py` | Fixed | Entry point over-detection fixed (session 3) |
| `viewer/graph.js` | Updated (untested) | Relation filters, data-flow trace, type structure panel |
| `serve.py` | Done | LOD server, no changes needed |
| `design.md` | Up to date | Full producer/consumer model documented |
| `analyze/flow_trace.py` | New (session 3) | Execution flow to Mermaid stateDiagram-v2 |
| `analyze/type_expander.py` | New (session 3) | Type to recursive struct tree |
| `HANDOFF_LOD_SERVER.md` | Stale | Superseded by this file |
| `HANDOFF_PRODUCER_CONSUMER.md` | This file | Updated session 3 |

---

## Design decisions recorded in design.md (do not re-litigate)

- `produces`/`consumes` connect symbols to **type nodes**, not symbol to symbol
- `uses_type` is the **undirected fallback** — never remove it, only add directed edges on top
- `relay:True` means "keep walking upstream, this symbol didn't originate the value"
- `role:control` means the input shapes behavior but its data doesn't appear in output
- Pointer depth on `contains` edges is structural metadata, not a new node type
- `typedef_of` is intra-language aliasing; `maps_to` is cross-language (already in schema)
- Compiler IR (clangd, pyright) is Tier 3/4 enrichment — same output schema, optional
