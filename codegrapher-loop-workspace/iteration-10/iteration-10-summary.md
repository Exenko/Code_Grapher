# Iteration 10 Summary — codegrapher-loop evals

Date: 2026-03-21

## Results

| # | File | Type | node_recall | edge_recall | hallucination | pass |
|---|------|------|-------------|-------------|---------------|------|
| 1 | migrate_add_seasonal_bucket.py | flowchart TB | 1.00 | 1.00 | 0.00 | **PASS** |
| 2 | certificate_signer.py | classDiagram | 1.00 | 1.00 | 0.00 | **PASS** |
| 3 | cuisine_hierarchy_sync.py | sequenceDiagram | 1.00 | 1.00 | 0.00 | **PASS** |
| 4 | create_tables_pg.py | flowchart TB | 1.00 | 1.00 | 0.00 | **PASS** |
| 5 | certificate_validator.py | classDiagram | 1.00 | 1.00 | 0.00 | **PASS** |

**Pass rate: 5/5 (100%)**

## Key findings per eval

### Eval 1: migrate_add_seasonal_bucket.py (flowchart TB) — PASS
Simple sqlite3 migration. Direct DB library calls (connect, cursor, execute, fetchall, commit, close) correctly included as terminal nodes. Exception-path rollback excluded per main-pipeline-only rule. Confirms the sqlite3 migration pattern established in iter 9 (create_local_tables.py).

### Eval 2: certificate_signer.py (classDiagram) — PASS
**Parameter/return type ≠ field type validated.** TokenCertificate is used as:
- RETURN TYPE of create_certificate() → no edge
- PARAMETER TYPE in sign_certificate() → no edge
- CertificateSigner.key_manager has NO type annotation → no edge
Graph has produces/consumes/modifies/calls edges between CertificateSigner and TokenCertificate — all correctly excluded by "field type only" classDiagram rule. 2 classes, 0 structural edges.

### Eval 3: cuisine_hierarchy_sync.py (sequenceDiagram) — PASS (Gap 1.5 probe)
**Confirmed Gap 1.5 scenario — instance method tracking rule sufficient.**
- Sub-graph has ZERO cross-file edges (all 13 edges intra-file)
- Constructor-injected deps: self.db = db_manager, self.server_client = server_client — NOT tracked by parser (Gap 1.5 not implemented)
- Skill agent correctly resolved types FROM DOCSTRINGS:
  - "db_manager: LocalDatabaseManager instance" → database_manager.py
  - "server_client: ServerClient instance for API calls" → server_client.py
- Private methods (_fetch_cuisine_version, _fetch_full_cuisine_hierarchy) suppressed as intra-file arrows, but their cross-file calls (server_client.get) correctly included
- After compression: 3 actors, 5 messages → GT match

**Conclusion: Gap 1.5 parser fix NOT needed.** The instance method tracking rule (read source + docstring type resolution) handles constructor-injected deps correctly.

### Eval 4: create_tables_pg.py (flowchart TB) — PASS
**Typed parameter annotation resolved by parser (confirmed).** `db_util: PostgresDatabaseUtility` parameter — all three method calls (execute, commit, create_partitions_for_climate_zones) appear in tier_symbol.json with cross_file=true. Gap 1 fix handles BOTH return-type tracking AND parameter-type annotation tracking.

**Sub-graph insufficiency finding:** For files without a `__main__` block (not standalone scripts), the referential sub-graph only has `defines` edges — ZERO cross-file call edges. Skill agent MUST use tier_symbol.json (not just sub-graph) to find actual call edges. A sub-graph-only approach would give node_recall=0.25 (FAIL).

**execute() compression:** Called 70+ times; graph emits ONE edge regardless of call count. Shared terminal node rule satisfied at graph level automatically.

**Unexpected:** create_partitions_for_climate_zones() captured in graph alongside expected execute/commit.

### Eval 5: certificate_validator.py (classDiagram) — PASS
**Raised exception ≠ structural edge validated.** CertificateError is defined in same file as CertificateValidator but:
- Never used as a field type in CertificateValidator
- Methods return (False, message) tuples rather than raising it
Skill correctly produces 2 classes, 0 structural edges. Same-file cohabitation ≠ structural relationship.

## Cumulative pass rates

| Iteration | Scope | Pass rate |
|---|---|---|
| Iteration 1 | Stress-test (C/C++/Proto/WSDL) | 15/15 (100%) |
| Iteration 2 | SmartRecipeApp (5 entries) | 4/5 (80%) |
| Iteration 3 | SmartRecipeApp (5 new) | 1/5 (20%) |
| Iteration 4 | SmartRecipeApp (3 v2 re-runs) | 4/4 (100%) |
| Iteration 5 | SmartRecipeApp (5 new) | 4/5 (80%) |
| Iteration 6 | SmartRecipeApp (1 v2 + 5 new) | 4/6 (67%) |
| Iteration 7 | SmartRecipeApp (2 v2 + 5 new) | 4/7 (57%) |
| Iteration 8 | SmartRecipeApp (3 v2 + 5 new) | 2/8 (25%) |
| Iteration 9 | SmartRecipeApp (3 v3 + 5 new) | 8/8 (100%) |
| **Iteration 10** | **SmartRecipeApp (5 new)** | **5/5 (100%)** |

## New findings — additions to SKILL.md / knowledge base

1. **Gap 1.5 closed (via docstring resolution):** Constructor-injected deps (self.x = param) are handled by reading source docstrings. No parser fix needed. Instance method tracking rule covers this case.

2. **Sub-graph vs tier_symbol.json:** For files without `__main__` (not standalone scripts), the referential sub-graph has only `defines` edges. Skill agent must use tier_symbol.json for actual call edges. This is a known structural limitation of the referential sub-graph design (sub-graphs follow entry points only).

3. **Parameter annotation tracking confirmed:** Typed parameters (`db_util: PostgresDatabaseUtility`) ARE resolved by the parser to cross-file edges — Gap 1 fix covers both return-type and parameter-type annotation resolution.

4. **Raised exceptions ≠ structural edges:** Custom exception classes defined in the same file as a validator/handler do NOT create classDiagram structural edges — raising/catching is runtime behavior, not field composition.
