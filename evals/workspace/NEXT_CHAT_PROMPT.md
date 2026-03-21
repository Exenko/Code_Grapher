# CodeGrapher — pick up from Iteration 10, run Iteration 11 evals

Check memory first (MEMORY.md → CodeGrapher section) for full context on the project before doing anything else.

---

## What was just completed (this session)

Iteration 10: 5 new entry points, all 5 PASS (100%).

---

## Iteration 10 results

| # | File | Diagram | Result |
|---|------|---------|--------|
| 1 | migrate_add_seasonal_bucket.py | flowchart TB | PASS |
| 2 | certificate_signer.py | classDiagram | PASS |
| 3 | cuisine_hierarchy_sync.py | sequenceDiagram | PASS |
| 4 | create_tables_pg.py | flowchart TB | PASS |
| 5 | certificate_validator.py | classDiagram | PASS |

Workspace: `C:\Users\Mike\.claude\codegrapher-loop-workspace\iteration-10\`

---

## Key findings from iteration 10

### Gap 1.5 closed (no parser fix needed)
cuisine_hierarchy_sync.py confirmed Gap 1.5 scenario: sub-graph has ZERO cross-file edges. Constructor-injected deps (self.db = db_manager, self.server_client = server_client) not tracked by parser. But skill agent correctly resolved types FROM DOCSTRINGS. Instance method tracking rule + docstring reading is sufficient. **Gap 1.5 parser fix deferred indefinitely.**

### Sub-graph vs tier_symbol.json
For files without `__main__` block (not standalone scripts), referential sub-graphs only have `defines` edges — ZERO cross-file call edges. Skill agent MUST use tier_symbol.json for actual call data. A sub-graph-only approach gives node_recall=0.25 for create_tables_pg.py (FAIL).

### Typed parameter annotation resolution confirmed
`db_util: PostgresDatabaseUtility` in create_tables_pg.py — all method calls have cross_file=true in tier_symbol.json. Gap 1 fix handles both return-type AND parameter-type annotation resolution.

### classDiagram rules validated under stress
- Parameter/return types correctly excluded: TokenCertificate used as param/return in CertificateSigner → 0 edges
- Raised exception correctly excluded: CertificateError raised in CertificateValidator → 0 edges

---

## Cumulative pass rates

| Iteration | Pass rate |
|-----------|-----------|
| Iter 1 | 15/15 (100%) |
| Iter 2 | 4/5 (80%, 1 known limitation) |
| Iter 3 | 1/5 (20%) |
| Iter 4 | 4/4 (100%) |
| Iter 5 | 4/5 (80%) |
| Iter 6 | 4/6 (67%) |
| Iter 7 | 4/7 (57%) |
| Iter 8 | 2/8 (25%) |
| Iter 9 | 8/8 (100%) |
| **Iter 10** | **5/5 (100%)** |

---

## What to do next

### Step 1 — Run Iteration 11 evals

5 new entry points. Good candidates:
- Files with async FastAPI route patterns (if any untested async routes exist)
- Multi-class files with genuine field-type relationships (test a 3+ class classDiagram with edges)
- Files that import from both Client_Side and Server_Side
- Server_Side scripts not yet tested

**Already tested (do not repeat):** autofill_engine, meal_plan_manager, seasonal_indexer, ingredients_routes, recipe_queue_manager, dummy_query_scheduler, recipe_yaml_converter, quick_setup, key_manager, overlap_optimizer (iter 5), sync_overlap_from_server, ingredient_analyzer, allergen_indexer, climate_ingredients_loader, ingredient_sync_manager (iter 6), preference_compiler, seasonal_calculator, master_ingredients_loader, cuisine_hierarchy_loader, sync.py (iter 7), local_recommender, overlap_sync_manager, reference_data_loader, populate_reference_data, recipe_entry_view (iter 8), lookup_loader, taxonomy_loader, ingredients route, create_local_tables, pg_database_utility (iter 9), migrate_add_seasonal_bucket, certificate_signer, cuisine_hierarchy_sync, create_tables_pg, certificate_validator (iter 10).

**Selection criteria:**
- AVOID sequenceDiagram for stdlib-only files (degenerate case)
- AVOID multi-file stateDiagram-v2 (known limitation)
- PREFER files where diagram type fits graph data well
- PREFER testing a 3+ class classDiagram with actual structural edges if one exists
- When using skill agent: use tier_symbol.json, NOT just sub-graph JSON, for files without `__main__`

### Step 2 — SKILL.md update (optional)
Consider adding a note to SKILL.md about sub-graph vs tier_symbol.json usage: "For non-entry-point files (no __main__ block), the sub-graph JSON only has defines edges. Use tier_symbol.json filtered by file path for actual call edges."

---

## Key files

```
CodeGrapher/parser_python.py       ← Gap 1 + Gap 2 + _direct_call_nodes helper
CodeGrapher/run.py                 ← return_type_map built by direct AST scan
C:\Users\Mike\.claude\codegrapher-loop\SKILL.md  ← all prompt rules
C:\Users\Mike\.claude\codegrapher-loop-workspace\iteration-10\  ← last eval results
```

Graph rebuild: `py CodeGrapher/run.py --feature repo --root . --dir Client_Side Server_Side test_scripts`
MCP server:    `py CodeGrapher/mcp_server.py --graphs CodeGrapher/graphs`
