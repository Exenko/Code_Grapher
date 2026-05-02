# CodeGrapher Backlog

Items deferred from the pre-release architecture review (2026-05-02). Priority order within each section.

---

## Architecture: Deferred from Pre-Release Review

These were identified as real friction but not release blockers. Implement after the initial public push.

### High Priority (safe to parallelize)

- [ ] **Extract `dedup_type_nodes_by_label` and `drop_ghost_nodes` into free functions**
  - Both are complex multi-step algorithms buried inside `CodeGraph` methods with no observable intermediate state
  - Extract to free functions (or a `GraphCleaner` class) that take and return a `CodeGraph`; existing methods become thin wrappers
  - Benefit: each algorithm gets its own tests; interface survives refactors to the graph data model
  - Files: `graph.py:89–209`

- [ ] **Add `node_id_tier()` to `schema.py` — decouple `serve.py` dispatch from ID format**
  - `_neighbors_response` in `serve.py` splits on `"::"` and counts parts to guess which tier file to load
  - Add a `node_id_tier(node_id: str) -> str` function to `schema.py` that returns the tier ("repo", "dir", "file", "symbol") from an ID
  - Benefit: ID format knowledge has one home; dispatch logic becomes a lookup; testable without an HTTP server
  - Files: `serve.py:56–91`, `schema.py`

- [ ] **Consolidate `type_expander.py` Mermaid renderer to two passes**
  - `_render_mermaid` runs three separate loops over the same data, each rebuilding information the others computed
  - Consolidate: one collection pass, one emit pass; eliminate the `_collect` wrapper and post-hoc `type_fields` rebuild
  - Benefit: all diagram assembly in one place; easier to add output formats (e.g. PlantUML) without touching collection logic
  - Files: `analyze/type_expander.py:451–567`

### Medium Priority (overhauls — review before merging)

- [ ] **Extract `TwoPassBuilder` from `run.py:main()`**
  - Pass 1 (registry build), return-type map, Pass 2 (call resolve) are inlined in `main()` (`run.py:104–228`)
  - The return type scan re-opens and re-parses every `.py` file after Pass 1, bypassing the parser layer
  - Extract to a class so the algorithm is testable and reusable (e.g. for incremental updates)
  - Files: `run.py:104–228`

- [ ] **Extract `EntryPointDetector` from `tiered_builder.py`**
  - 19 hard-coded path/filename patterns checked in a sequential if/elif chain with no override mechanism
  - Extract to a class with `detect(file_nodes) -> list[FileNode]`; patterns become data
  - Benefit: detection logic is independently testable; adding a new language's entry point convention is one list append
  - Files: `tiered_builder.py:30–174`

- [ ] **Wrap MCP global graph state in `GraphSession`**
  - `active_graph` is a module-level global; two concurrent Claude sessions clobber each other
  - Wrap graph state in a `GraphSession` object; tools take a session parameter; single global session remains the default
  - Benefit: limitation becomes fixable without rewriting all 13 tools; tests can create isolated sessions
  - Files: `mcp_server.py:70–84`, `mcp_server.py:356–402`

---

## Architecture: Carry-over from Previous Review

- [ ] **Test call resolution** — `graph.resolve_calls()` once extracted
  - Unresolved → resolved edge upgrade when target appears in registry
  - Edge case: symbol in registry but no matching edge

- [ ] **Test graph merge + dedup**
  - Merging two graphs with overlapping nodes
  - Type node dedup by label
  - Same edge added twice with different metadata

- [ ] **Fix return type map double-parsing** (`run.py:140–165`)
  - Re-opens and re-parses every `.py` file after Pass 1 just to extract return type annotations
  - `produces` edges already capture this info — extract from graph instead

- [ ] **Add `CodeGraph.subgraph_by_symbols(symbol_ids)`**
  - `tiered_builder._build_sub_graph()` manually filters edges — this is a graph operation that belongs on `CodeGraph`
  - Files: `graph.py`, `tiered_builder.py:220–363`

---

## Capability Gaps

- [ ] **UI: consolidate side panels into tabs**
  - Flowchart, data flow, and state diagram as tabs in one right panel rather than separate overlay modes

- [ ] **State machine transitions**
  - `state_ = State::RUNNING` → MODIFIES edge to enum; no concept of state transition edges between enum values
  - Park until after callback tracing is complete
