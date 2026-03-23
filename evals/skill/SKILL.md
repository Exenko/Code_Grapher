---
name: codegrapher-loop
description: Run, verify, and improve CodeGrapher parsers against the stress-test ground truth. Use this skill whenever the user wants to run CodeGrapher, check graph output, fix a parser, verify node/edge counts, improve parse quality, or work on the eval loop. Also use it when the user asks to "graph" a codebase, run the stress test, check CodeGrapher results, or evaluate MCP tool accuracy. This skill captures the full verify-fix-repeat loop for CodeGrapher development, including how to run evals using the MCP server as a two-agent comparison.
---

# CodeGrapher Development Loop

CodeGrapher is an AST-based codebase cartography tool that produces graph JSON files.
The core dev loop: **run parser → compare against ground truth → identify gaps → fix parser (general-purpose only, never tailored to the test) → repeat.**

## Quick orientation

```
Repo root: c:\Users\Mike\Documents\GitHub\Code_Grapher\

Stress-test codebase:  stress_tests/         (C++, proto, XML, Java, Kotlin)
Ground truth:          GT/stress_tests/GROUND_TRUTH.md
Parser sources:        CodeGrapher/parser_cpp.py
                       CodeGrapher/parser_proto.py
                       CodeGrapher/parser_xml.py
                       CodeGrapher/parser_python.py
                       CodeGrapher/parser_java.py
                       CodeGrapher/parser_kotlin.py
                       CodeGrapher/parser_typescript.py
Graph engine:          CodeGrapher/graph.py
Schema:                CodeGrapher/schema.py
MCP server:            CodeGrapher/mcp_server.py

Graph output dir:      graphs/
  feature_stress.json  <- the stress-test graph (always rebuild before checking)
  toc.json             <- index, loaded by MCP server at startup
  tier_*.json          <- LOD tiers
  sub/                 <- per-entry-point referential sub-graphs
```

## How to run

```bash
# Rebuild stress-test graph
py CodeGrapher/run.py --feature stress --root . --dir stress_tests

# Rebuild full repo graph (project-specific path)
py CodeGrapher/run.py --feature repo --root . --dir Client_Side Server_Side test_scripts

# Start MCP server (for eval agent queries)
py CodeGrapher/mcp_server.py --graphs graphs

# Start LOD viewer
py CodeGrapher/serve.py --graphs graphs   # http://localhost:5000
```

## Ground truth checklist

After each rebuild, verify against `GT/stress_tests/GROUND_TRUTH.md`:

| Assertion | Expected |
|---|---|
| File nodes | 44 |
| Symbol nodes | 328 |
| Type nodes | 60 |
| `calls` edges | 247 |
| `typedef_of` edges | 4 |
| `maps_to` edges | 6 |
| `modifies` edges | 100 |
| `unresolved` call edges | 72 (stdlib + intra-feature) |
| Entry points | 3 (producer/main.cc, broker/main.cc, consumer/main.cc) |

Quick Python check:
```python
import json
from collections import Counter
d = json.load(open("graphs/feature_stress.json"))
print("nodes:", Counter(n["type"] for n in d["nodes"]))
print("edges:", Counter(e["relation"] for e in d["edges"]))
```

## The verify-fix-repeat loop

1. **Run** the graph builder
2. **Check** node/edge counts against the checklist above
3. **Identify** the gap (wrong count? missing relation? wrong node type?)
4. **Read** the relevant parser source and the ground truth section that describes the expected output
5. **Fix** the parser — keeping it general-purpose (no stress-test-specific hacks)
6. **Re-run** and re-check

**Rule:** Parsers must remain general-purpose. Never add a special case to make the stress test pass that wouldn't also make sense for arbitrary real-world code.

## Parser responsibilities

| Parser | Languages | Key semantic layer |
|---|---|---|
| `parser_cpp.py` | C/C++, `.h/.cc` | structs, enums, typedefs, functions, calls; relay:true for broker files |
| `parser_proto.py` | `.proto` | messages, enums; generates/defines/contains/maps_to |
| `parser_xml.py` | WSDL/XSD/config `.xml` | complexType→TYPE; portType→SYMBOL; configures/maps_to |
| `parser_python.py` | Python | 2-pass AST; Tier 1 (signature) + Tier 2 (body walking); produces/consumes/relay/seq |
| `parser_java.py` | Java `.java` | 2-pass regex; class/method/field nodes; calls, consumes, produces, uses_type |
| `parser_kotlin.py` | Kotlin `.kt` `.kts` | 2-pass regex; data class, sealed class, companion object, suspend fun; same edge set as Java |

Edge semantics: `produces` = data emitter, `consumes` = data consumer, `calls` = control flow, `modifies` = in-place mutation of a typed parameter, `typedef_of` = type alias chain, `maps_to` = cross-format equivalence (proto↔WSDL↔C++), `relay:true` = broker/pass-through node.

**`modifies` edge:** Emitted when a function mutates a typed parameter in-place (e.g., a `T*`/`T&` non-const pointer/reference in C++, or a Python parameter that is annotated AND mutated via attribute assignment or mutating method calls like `.append()`/`.update()`). When drawing flowchart or sequence diagrams, a `modifies` edge signals that the called function transforms the input object — show it as a data transformation step (e.g., a node labelled `transform(obj)` or an arrow annotated `modifies`). In classDiagram, `modifies` is not used for structural edges — it is a runtime behavioral signal only.

## Haiku sub-agent discipline

Use **Haiku** for parser exploration and implementation sub-agents.
Use **main context (Sonnet/Opus)** for critical reasoning: deciding what to fix, reviewing diffs, evaluating whether a fix is general vs. tailored.

Typical sub-agent task pattern:
```
Read CodeGrapher/parser_cpp.py lines N-M.
Read CodeGrapherStressTest/broker/relay.cc.
Explain why relay:true edges are not being emitted for broker files.
Do NOT propose a fix yet — just diagnose.
```
Then reason about the fix in main context before applying.

## Eval loop (Phase 3)

Read `references/eval_design.md` for the full eval specification.

**Short version:** Two agents compare data-flow diagrams for each of the 3 entry points:
- **Ground-truth agent** — reads source files directly, produces Mermaid diagram by hand
- **Skill agent** — queries mcp_server.py tools only, produces Mermaid from tool output

Metrics: node recall, edge recall, hallucination rate.

See `evals/evals.json` for the three eval cases (eval-broker, eval-consumer, eval-producer).

---

## Diagram type rules (validated in iterations 3–4)

These rules apply when using the skill agent to produce Mermaid diagrams from graph data.
They are language/codebase agnostic and must be followed regardless of what entry point is being diagrammed.

### classDiagram

**Edge rule:** Draw edges ONLY when class A has a field whose declared type is class B.
- Do NOT draw edges from `produces`/`consumes` function I/O (pipeline dependencies are not structural relationships).
- Do NOT draw edges from file proximity or imports.
- Check before drawing any edge: is B listed as a field type in A's class body?

**Generic container type rule:** For fields typed as generic containers (`List[T]`, `Dict[K,V]`, `Set[T]`, `Optional[T]`), the CONTAINER is the declared type — not the type parameter. Do NOT draw edges because a local class appears only as a type parameter. Examples:
- `pattern_map: Dict[str, AllergenHierarchy]` — declared type is `Dict` → NO edge
- `items: List[Recipe]` — declared type is `List` → NO edge
- `field: AllergenHierarchy` — declared type IS the local class → DRAW edge
- `field: Optional[AllergenHierarchy]` — Optional wrapping a local class directly → DRAW edge (treat as direct reference)

*Validated on: allergen_indexer.py (iter 6 failure) — skill incorrectly drew edge via Dict[str, AllergenHierarchy] type parameter. GT correctly had 0 edges.*

**Multi-file scan rule (iter 8):** When a class in the primary file has fields typed as local project classes defined in OTHER files, read those imported project files too. Include classes from imported project files in the classDiagram if they are used as field types. Do NOT include stdlib or third-party classes (QFrame, QWidget, etc.) as classDiagram nodes. Example: if `IngredientRowWidget` uses `AutocompleteEntryEnhanced` (from `autocomplete_entry.py`) as a field type, read `autocomplete_entry.py` and include `AutocompleteEntryEnhanced` in the diagram.

*Iter 8: recipe_entry_view failed (node_recall=0.29) — skill only read recipe_entry_view.py and found 2 classes, missing 5 imported project classes (AutocompleteEntryEnhanced, EnhancedAutocompletePopup, NumericEntry, YamlPreviewDialog, RecipeYamlConverter) and the 1 structural edge between them.*

Validated on: autofill_engine.py (eliminated 10/12 hallucinated dataflow edges), meal_plan_manager.py (eliminated 3 hallucinated enum/internal-only edges).

### stateDiagram-v2 (single-file only)

**Cleanup/eviction rule:** If a method name suggests cleanup, eviction, or overflow handling (e.g., `_cleanup_queue`, `evict`, `overflow`), draw a direct `State --> [*]` transition. Do NOT insert intermediate sub-states between the active state and the terminal.

**Re-entry rule:** If source code comments or method logic indicate an item can be re-added after a terminal-looking state (e.g., `Served -> Active`), draw the re-entry edge explicitly.

**No elaboration rule:** Do not insert intermediate sub-states not derivable from the class body or graph data. If the graph edge says `State --> [*]`, draw exactly that.

**Filter method rule:** Query/filter methods (e.g., `get_pending_queries()`, `get_active_*()`, `fetch_*()`) represent SQL WHERE filters applied to existing states — they do NOT create new states and do NOT introduce state transitions. Only methods that UPDATE or DELETE the status field create state transitions. If a method name starts with `get_`, `fetch_`, `find_`, `load_`, or `query_`, treat it as an observer — exclude it from the state machine.

*Validated on: dummy_query_scheduler.py — get_pending_queries() is WHERE executed=FALSE AND scheduled_time<=now; inserting a "Pending" intermediate state from this filter method was a hallucination (iter 5 failure).*

Multi-file stateDiagram-v2 is UNSUPPORTED — granularity mismatch between call-edge graphs and state abstraction is unresolvable.

Validated on: recipe_queue_manager.py (removed EXPIRED sub-state, added Served->Active re-entry and Active->[*] overflow eviction).

### flowchart TB / LR (call graph)

**GT calibration rule:** Ground truth for flowchart diagrams must be written at method-level granularity — one node per function call. Do NOT write statement-level ground truths that include branching guards, loop counters, or conditional guards. The graph parser captures calls/produces/consumes but NOT intra-method control flow.

**Skill agent rule:** Produce one node per function/method call. Do not invent branching logic or loop counters not present in the graph edge data.

**Cross-file terminal nodes rule:** For flowchart diagrams, ALL method calls that cross file boundaries MUST appear as terminal leaf nodes. When reading source code, identify every method call on objects from imported modules (e.g., `db_util.connect()`, `db.execute()`, `db.commit()`, `db.fetch_one()`, `self.db.*`). Include these as leaf nodes labeled `<object>.<method>()` even if the graph JSON did not capture them. Do not omit cross-file calls just because they appear inside a loop or are repeated.

**Shared terminal node rule (iter 8):** Use ONE shared terminal node per distinct cross-file method name. Do NOT create duplicate nodes (e.g., db_connect1, db_connect2, db_execute1, db_execute2). Multiple callers all point to the SAME terminal node. Example: if both `load_ingredients()` and `generate_report()` call `db_util.connect()`, show ONE `db_util.connect()` node with arrows from both callers.

**Main pipeline only rule (iter 8):** Show ONLY the primary execution pipeline. Exclude: initialization helper chains not on the main call path, exception paths and rollback handlers (omit `db.rollback()` in try/except unless architecturally central), standalone report/utility methods, dead code.

**Stdlib exclusion rule (iter 8):** `json.load()`, `open()`, `Path.exists()`, `yaml.load()`, `csv.reader()` are NOT cross-file terminal nodes. Only include project-internal utilities (`db_util.*`, `server_client.*`) and direct DB library calls (`sqlite3.connect()`, `cursor.execute()`, `conn.commit()`, `conn.close()`). File I/O stdlib is not a terminal node.

*Validated on: master_ingredients_loader.py + cuisine_hierarchy_loader.py (iter 7 failure) — skill showed intra-file method chain but omitted db_util.connect/commit/execute/close terminal nodes, causing node_recall of 0.64 and 0.43 respectively.*

*Iter 8: master_ingredients_loader + cuisine_hierarchy_loader v2 still failed (hallucination 0.74, 0.43) due to duplicate terminal nodes and extra non-pipeline methods. Fixed by shared-node + main-pipeline-only rules above.*

*Iter 8: reference_data_loader failed (hallucination 0.25) from including json.load, open, Path.exists. Fixed by stdlib exclusion rule.*

Validated on: seasonal_indexer.py (GT recalibrated from 72-node statement-level to 12-node method-level; skill output was already correct at method-level granularity).

### sequenceDiagram

**Actor rule:** Each actor maps to a distinct PYTHON SOURCE FILE (use cross_file_edges to identify files touched). Do not merge actors from different files.

**Python files only rule:** Actors MUST be Python .py source files. HTTP clients, database servers (PostgreSQL, SQLite, Redis), external APIs, and framework infrastructure (FastAPI, Django) are NOT actors and must NOT appear as participants. If you are tempted to add a "Client" or "Database" participant — do not.

**No library traversal rule:** Show only the entry point file's outgoing calls to other files. Do NOT trace into what the called files do internally. If `sync.py` calls `pg_database_utility.execute()`, show `sync → pgutil: execute()` only. Do NOT show `pgutil → database: execute query` or any other arrows originating from the called file.

*Validated on: sync.py (iter 7 failure) — skill added FastAPI Client and PostgreSQL DB as actors (not Python files), and showed pg_database_utility's internal database calls. All GT calls were present but hallucination = 0.63 from over-elaboration.*

**Ordering rule:** Use the `seq` field on call edges to determine message ordering. If no `seq` field, use graph traversal order.

**Alt/loop rule:** Include `alt` blocks when the graph contains branching call patterns to the same callee from different conditional paths.

**No self-messages rule:** Never draw Actor→Actor arrows where source and target are the same file. Internal return/error states, local variable assignments, and control flow decisions are intra-file — they are NOT cross-file messages and must not appear as sequence arrows.

**Repeated-call compression rule:** If the same cross-file method is called multiple times within a loop or across parallel conditional branches (e.g., `_get_connection()` called inside DELETE, INSERT, and UPDATE all in the same conditional block), show ONE representative call (or use a `loop` block) rather than separate arrows for each invocation. Goal: show the PATTERN, not every call site.

**Intra-file private method rule:** Calls of the form `self._privateMethod()` where `_privateMethod` is defined in the SAME file are intra-file. Do NOT show these as cross-file messages. Only `self.<injected_dependency>.method()` calls (where the dependency is an instance of a class from another file) are cross-file.

*Validated on: ingredient_sync_manager.py (iter 6 failure) — skill added ISM→ISM self-messages, intra-file _get_local_sync_state, and multiple _get_connection instances, causing hallucination rate of 0.24.*

**Instance method tracking rule (iter 8):** When a local variable holds an instance RETURNED from another Python file (e.g., `db = get_database()` returns a `PostgresDatabaseUtility` from `pg_database_utility.py`), ALL method calls on that variable (`db.execute()`, `db.fetchall()`, `db.commit()`) are cross-file messages to that returned object's file. Read the source to identify the return type, then show `caller → returned_file: method()`.

**Degenerate case rule (iter 8):** If the entry point has NO cross-file calls to other project Python files (e.g., it only uses stdlib: sqlite3, json, hashlib), produce a diagram with ONLY the entry file as participant and ZERO messages. Do NOT invent test harnesses or callers. Example: `sequenceDiagram\n    participant self as overlap_sync_manager.py` with no arrows.

*Iter 8: sync.py v2 failed (edge_recall=0.33) — agent did not trace db.execute()/db.fetchall() as cross-file calls to pg_database_utility.py because graph parser doesn't create edges for instance methods on returned objects. Agent must read source to identify return type and include those calls. Fixed by instance method tracking rule.*

*Iter 8: overlap_sync_manager failed (hallucination=0.67) — agent invented a test_sync_manager caller. Fixed by degenerate case rule.*

Validated on: Server_Side/api/app.py (100% recall), Server_Side/api/ingredients_routes.py (80%/85%, PASS).
