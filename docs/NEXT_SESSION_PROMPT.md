# CodeGrapher — Next Session Prompt

## Context

CodeGrapher is an AST-based codebase cartography tool. It parses Python, C/C++, Protobuf, XML,
TypeScript/JavaScript, Java, and Kotlin into a graph of nodes (files, symbols, types) and edges
(calls, defines, imports, modifies, etc.), then serves them as tiered JSON and an interactive
LOD viewer.

Repo layout:

```text
Code_Grapher/
  CodeGrapher/        ← all tool source (run.py, parsers, serve.py, mcp_server.py, etc.)
    parser_typescript.py
    parser_java.py
    parser_kotlin.py
    analyze/          ← flow_trace.py, type_expander.py
    viewer/           ← D3 LOD viewer static assets
  stress_tests/       ← multi-language stress test corpus
    broker/           ← C++ broker (relay, router, state machine)
    consumer/         ← C++ consumer (decoder, processor, output)
    producer/         ← C++ producer (encoder, callbacks, state machine)
    proto/            ← Protobuf messages (messages.proto, events.proto, legacy.proto)
    wsdl/             ← XML/WSDL (legacy_service.xml, legacy_types.xml)
    config/           ← XML config (broker_config.xml, producer_config.xml)
    inherit/          ← C++ inheritance stress test (base.h, derived.h, derived.cc)
    java/             ← Java client layer (MessageClient, EventSubscriber, LegacyAdapter, ServiceOrchestrator)
    kotlin/           ← Kotlin Android bridge layer (BrokerConnection, EventProcessor, SessionManager, AndroidBridge)
  evals/
    skill/            ← SKILL.md and eval harness for the codegrapher-loop LLM eval
    workspace/        ← iterations 1-10 of eval runs (ground truth + outputs)
    skill_outputs/    ← 3 sample skill outputs from SmartRecipeApp
  docs/               ← SPEC.md, design.md, HANDOFF notes
  GT/                 ← gitignored, ground truth working files
    stress_tests/     ← GROUND_TRUTH.md for the stress test corpus
```

Key run commands:

```bash
py CodeGrapher/run.py --feature <name> --root . --dir <dirs>
py CodeGrapher/serve.py --graphs graphs
py CodeGrapher/mcp_server.py --graphs graphs
```

Graphs output to `./graphs/` (CWD-relative, gitignored).

Note: `--dir` is relative to `--root`. To run against an external project:

```bash
py CodeGrapher/run.py --feature full --root C:/path/to/project --dir .
```

Optional flag (TS/JS and Python):

```bash
py CodeGrapher/run.py --feature full --root C:/path/to/project --dir . --no-stdlib-calls
```

---

## Phase Status

- Phase 1 complete — all parsers + graph engine
- Phase 2 complete — MCP server with 8 tools
- Phase 3 complete — eval harness (codegrapher-loop skill), 10 iterations, 100% pass rate
- Phase 4 in progress — language support complete for Python, C/C++, Proto, XML, TS/JS, Java, Kotlin; improvements ongoing

---

## What Was Done Last Session (2026-03-22)

### MCP server — 2 new tools

- `find_symbol(name_substring)` — searches all SYMBOL nodes by label substring (case-insensitive),
  returns matching nodes with their full incoming/outgoing edge sets. Mirrors `find_type`.
- `get_file_symbols(file_path)` — given a file path substring, returns all symbols and types
  defined in the matched file(s) with outgoing edges. One-call shortcut vs. repeated `expand_node`.
- MCP server now has 8 tools total.

### Ghost node filter — `drop_ghost_nodes()` in `graph.py`

- Added `CodeGraph.drop_ghost_nodes()`: strips all edges whose endpoints match the two unresolved
  patterns: `unresolved::*` (C++, Python, TS, Proto) and `*::_unresolved_.*` (Java, Kotlin).
- Called in `run.py` after `dedup_type_nodes_by_label()` and before `save()`.
- Effect on stress corpus: 68 ghost endpoints stripped, removing all unresolved call edges that
  pointed to synthetic targets. Viewer and MCP no longer see dangling edge endpoints.
- Side effect: regression target updated (see below) — the old `calls=340` included unresolved
  edges; the new `calls=245` reflects only edges between real nodes.

### SKILL.md ground truth updated

- Node counts corrected: 44 file / 328 symbol / 60 type.
- `calls` edges updated, `modifies=100` row added.
- Run path corrected to `--dir stress_tests`.

### Regression target updated

```text
calls=247, typedef_of=4, maps_to=6, modifies=100, unresolved=72
```

Run: `py CodeGrapher/run.py --feature stress --root . --dir stress_tests`

Notes on the current regression numbers:
- `calls=247` — resolved calls only. +2 from super.method() resolution (AndroidBridge.onCreate/onTerminate → ApplicationBase).
- `unresolved=72` — 43 `stdlib::` (Java/Kotlin external packages) + 29 `stress::` intra-feature
  edges that pass-2 couldn't resolve (pre-existing gap, not a regression).
- `modifies=100`, `consumes=100`, `produces=55` also visible in summary output.

### Session 2026-03-22 continued — full backlog completed

- `search` MCP tool added — unified SYMBOL+TYPE label search in one call. MCP server now has 9 tools.
- `summarize_entry_point` gains `follow_relations` param (default `["calls"]`); data-pipeline codebases can add `produces`/`consumes`.
- Python `self.member.method()` resolution — `visit_AnnAssign` now seeds `_instance_attr_types` from class-level type annotations (e.g. `conn: DatabaseConnection`), enabling resolution in all methods of the class.
- TypeScript MODIFIES edges — `_is_mutable_ref_type` (Ref<T>, MutableRefObject<T>, Dispatch<T>, etc.) and `_is_mutating_param_name` (set*, update*, mutate*, etc.) helpers wired into `_process_params`. Zero regression impact (stress corpus has no TS MODIFIES candidates by design).
- Java/Kotlin eval ground truth — 3 new eval cases added to `evals/skill/evals/evals.json` (IDs 4–6): ServiceOrchestrator.start, AndroidBridge.onCreate, EventProcessor.process.
- Java/Kotlin `super.method()` resolution — both parsers now build `class_supertypes` map during class parsing; resolution tries each supertype before falling back to same-class lookup. +2 resolved edges in stress corpus.
- SKILL.md updated: corrected repo root, paths, calls count (247), added Java/Kotlin parser rows.
- Regression target: `calls=247, typedef_of=4, maps_to=6, modifies=100, unresolved=72`.

---

## Prioritized Improvement Backlog

All backlog items completed. Remaining gaps are fundamental AST limitations (unannotated DI, chained property calls through destructuring, C++ `->` chains through containers) — not fixable without type inference.

---

## Known Limitations (permanent / out of scope)

**Python:**

- Unannotated dependency injection — requires type inference, not AST-solvable
- Method chains on untyped member variables — same root cause (backlog item 5 covers the *typed* case)

**C++:**

- Inherited method calls from out-of-scope base classes (JUCE framework) — expected
- `->` dereference chains through containers — would require nested struct member tracking

**TypeScript/JS:**

- Chained property calls (`vescState.setters.setXXX()`) unresolved — requires type inference
  through destructuring, same class as Python unannotated DI
- External package symbols (RN, third-party) unresolved — expected/correct

---

## Ground Rules

### Language-agnostic and project-agnostic

Every fix must be justified by general correctness. No hardcoded project names, paths, or
heuristics tuned to a specific codebase. The stress test corpus (`stress_tests/`) is the
canonical regression target.

### Orchestration model

- Main context (Sonnet): decisions — what to fix, whether a fix is general vs. tailored,
  reviewing diffs, grading output quality
- Haiku sub-agents: all file reading, exploration, command execution, code edits
- Delegate aggressively to keep main context clean

### Regression gate

After every engine change, run:

```bash
py CodeGrapher/run.py --feature stress --root . --dir stress_tests
```

Verify: `calls=247, typedef_of=4, maps_to=6, modifies=100, unresolved=72`.
Any change is a regression until proven otherwise.

### No new files without agreement

State what the file will be and why it can't go in an existing file. Wait for confirmation.
