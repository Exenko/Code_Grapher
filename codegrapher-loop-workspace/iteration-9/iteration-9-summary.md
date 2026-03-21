# Iteration 9 Summary — codegrapher-loop evals

Date: 2026-03-21

## Results

| # | File | Type | node_recall | edge_recall | hallucination | pass |
|---|------|------|-------------|-------------|---------------|------|
| 1 | master_ingredients_loader.py v3 | flowchart TB | 1.00 | 1.00 | 0.00 | **PASS** |
| 2 | cuisine_hierarchy_loader.py v3 | flowchart TB | 1.00 | 1.00 | 0.00 | **PASS** |
| 3 | sync.py v3 | sequenceDiagram | 1.00 | 1.00 | 0.00 | **PASS** |
| 4 | lookup_loader.py v1 | flowchart TB | 1.00 | 1.00 | 0.00 | **PASS** |
| 5 | taxonomy_loader.py v1 | flowchart TB | 1.00 | 1.00 | 0.00 | **PASS** |
| 6 | ingredients.py (route) v1 | sequenceDiagram | 1.00 | 1.00 | 0.00 | **PASS** |
| 7 | create_local_tables.py v1 | flowchart TB | 1.00 | 1.00 | 0.00 | **PASS** |
| 8 | pg_database_utility.py v1 | classDiagram | 1.00 | 1.00 | 0.00 | **PASS** |

**Pass rate: 8/8 (100%)**

## V3 re-run analysis

### master_ingredients_loader.py v3 — PASS (was: hallucination 0.74)
Fixed by:
- **Shared terminal node rule**: ONE `db_util.execute` node shared between `_ensure_database_structure` and `_insert_ingredients`
- **Main pipeline only rule**: excluded `_load_hierarchy`, `_validate_hierarchy`, `setup_logging`, `_extract_ingredients_from_category` (not on main call path from `load_ingredients`)
- **Stdlib exclusion rule**: excluded `yaml.safe_load`, `open`, `Path.exists`

### cuisine_hierarchy_loader.py v3 — PASS (was: hallucination 0.43)
Fixed by:
- **Shared terminal node rule**: ONE `db.commit` node serving `load_hierarchy` and `_insert_node`
- **Main pipeline only rule**: excluded `_load_data` (called in `__init__`, not main pipeline), `generate_report` (standalone utility)
- Cross-file terminal nodes `db.execute`, `db.commit`, `db.fetch_one` correctly identified via cross-file-terminal-nodes rule

### sync.py v3 — PASS (was: edge_recall 0.33)
Fixed by:
- **Gap 1 parser fix**: graph NOW has resolved cross-file edges `get_data_versions → PostgresDatabaseUtility.execute/fetchall/close`
- **Instance method tracking rule**: skill agent correctly read resolved edges from tier_symbol.json instead of needing "read source" workaround
- `unresolved::PostgresDatabaseUtility::connect` (cross_file=false) correctly omitted

## New entry point findings

### Evals 4-7: flowchart TB pattern solidifying
lookup_loader, taxonomy_loader, create_local_tables all passed cleanly. Pattern is fully established:
- Identify main pipeline function (not `__init__`, not `generate_report`)
- Include ALL cross-file DB method calls as shared terminal nodes
- Exclude: stdlib file I/O, error handlers, initialization helpers not on main call path
- Include: `sqlite3.connect()` (direct DB library call, not stdlib exclusion)

### Eval 6: sequenceDiagram with Gap 1 edges — PASS
ingredients.py route uses same `db = get_database()` pattern as sync.py.
Graph has resolved edges to `PostgresDatabaseUtility.execute/fetchall/fetchone/close` — skill agent read them correctly.
Repeated-call compression rule applied: two endpoints compressed to representative calls.

### Eval 8: classDiagram with 0 edges — PASS (vacuous)
pg_database_utility.py: 1 class, 0 edges (pool is ThreadedConnectionPool from psycopg2 — third-party, not project class).
Consistent with local_recommender pattern from iteration 8.

## Cumulative pass rates

| Iteration | Scope | Pass rate |
|---|---|---|
| Iteration 1 | Stress-test (C/C++/Proto/WSDL) | 15/15 assertions (100%) |
| Iteration 2 | SmartRecipeApp (5 entries) | 4/5 (80%, 1 known limitation) |
| Iteration 3 | SmartRecipeApp (5 new entries) | 1/5 (20%) |
| Iteration 4 | SmartRecipeApp (3 v2 re-runs) | 4/4 (100%) |
| Iteration 5 | SmartRecipeApp (5 new entries) | 4/5 (80%) |
| Iteration 6 | SmartRecipeApp (1 v2 + 5 new) | 4/6 (67%) |
| Iteration 7 | SmartRecipeApp (2 v2 + 5 new) | 4/7 (57%) |
| Iteration 8 | SmartRecipeApp (3 v2 + 5 new) | 2/8 (25%) |
| Iteration 9 | SmartRecipeApp (3 v3 + 5 new) | 8/8 (100%) |

## Parser improvements this session (pre-iteration 9)

Two bugs fixed in the Gap 1 implementation (run.py + parser_python.py):

**Bug 1 — return_type_map was always empty:**
`_emit_return_type_edge` calls `_resolve_type(tname)` which searches `self.known`. In Pass 1 `known=set()`, so the edge was never emitted, leaving the map empty. Fixed in run.py: replaced edge-based extraction with direct AST scan of Python source files for return annotations. Now 108 functions in the map.

**Bug 2 — double-processing in _walk_body:**
`ast.walk(outer_try_stmt)` fires all nested calls (including `db.execute()`) before the inner `db = get_database()` assignment tracking sets `_local_var_types["db"]`. This produced both unresolved (old path) and resolved (recursion path) edges for the same call. Fixed: added `_direct_call_nodes(stmt)` helper that only yields calls from expression-level parts of statements — block bodies are handled exclusively by recursion.

Result: 45 new resolved cross-file edges to pg_database_utility.py across the codebase.
