# CodeGrapher Iteration 2 — Feature Flow & State Diagram Evals

Check memory (`project_codegrapher_phase3.md`) before starting.

---

## Orchestration rules

- You are the orchestrating model. Delegate ALL file reads, writes, and graph queries to Haiku sub-agents. Never read or write files yourself.
- Use main context only for: deciding scope, reviewing Haiku outputs, grading, deciding what to fix.
- One Haiku agent per task. Maximize parallelism where tasks are independent.
- Haiku agents will return results to you — you write the output files (they lack write permissions).

---

## Background

CodeGrapher is an AST/regex graph tool that parses codebases into nodes (files, symbols, types) and edges (`calls`, `produces`, `consumes`, `typedef_of`, `maps_to`). The MCP server exposes 5 tools to query the graph. The eval loop tests whether a **skill agent** using only MCP tools can reconstruct the same diagram as a **ground-truth agent** reading source directly.

Iteration 1 (complete, 15/15 pass) tested `flowchart LR` data-flow diagrams for 3 stress-test entry points (broker, consumer, producer). Workspace: `C:\Users\Mike\.claude\codegrapher-loop-workspace\iteration-1\`.

**Core insight for iteration 2:** Every `if __name__ == "__main__"` is a feature entry point. The graph should be able to reconstruct the call chain, data flow, and/or state transitions for any such entry point. That's what we're testing.

---

## Diagram type selection

The diagram type must match the *nature* of the feature. Ground-truth agents choose the best type and justify it. Skill agents use the same type.

| Feature type | Diagram type |
|---|---|
| Call chain / data pipeline | `flowchart LR` or `flowchart TB` (TB for top-down pipelines) |
| Auth flow / view routing / FSM | `stateDiagram-v2` |
| Request/response, API protocol | `sequenceDiagram` |
| Class hierarchies, type relationships | `classDiagram` |
| Database schema / FK relationships | `erDiagram` |
| App architecture / service boundaries | C4 context |
| Deep nested chains with natural groupings | `flowchart LR` with `subgraph` blocks |
| User-facing workflows | `journey` |

**Recommended types for iteration 2 entry points:**

| Entry point | Recommended type | Reason |
|---|---|---|
| `Client_Side/main.py` | `stateDiagram-v2` | Auth states: UNINITIALIZED → AUTHENTICATING → AUTHENTICATED/UNAUTHENTICATED |
| `Client_Side/ui_new/run_ui.py` | `flowchart LR` | Linear startup call chain |
| `Server_Side/main.py` | `flowchart LR` with subgraphs | 10-step pipeline, groups naturally by phase |
| `Server_Side/api/app.py` | `sequenceDiagram` | Client → Flask → DB → response, temporal ordering matters |
| `Server_Side/db/overlap_indexer.py` | `flowchart TB` | Top-down pipeline stages |

Ground-truth agents may override the recommendation if source analysis reveals a better fit — they must justify the choice in their output.

---

## Entry points to evaluate

1. `Client_Side/main.py` — app startup: auth check → view routing (login vs dashboard)
2. `Client_Side/ui_new/run_ui.py` — UI entry point and window setup
3. `Server_Side/main.py` — DB initialization pipeline (10-step sequential, circuit-breaker pattern)
4. `Server_Side/api/app.py` — Flask API request routing and endpoint structure
5. `Server_Side/db/overlap_indexer.py` — ingredient overlap data pipeline

---

## Step 1 — Ground truth (parallel, one Haiku agent per entry point)

Each agent:
1. Reads the relevant source files (entry point + key callees, up to ~5 files)
2. Chooses the best diagram type (use recommendations above, justify if overriding)
3. Produces a complete Mermaid diagram with:
   - All key symbols in the call/data chain
   - Edges labeled with relation type (`calls`, `produces`, `consumes`, state transitions, HTTP verbs, etc.)
   - Guards/conditions on transitions where present
   - Subgraphs for logical groupings where appropriate
4. Returns: diagram type chosen, the Mermaid block, and a short justification

You (orchestrator) write results to:
```
C:\Users\Mike\.claude\codegrapher-loop-workspace\iteration-2\ground-truth\{name}\ground_truth.md
```
Names: `client_main`, `client_ui`, `server_main`, `server_api`, `overlap_indexer`

Format for each ground_truth.md:
```markdown
# Ground Truth — {entry point}

**Diagram type:** {type} — {one-line justification}

**Key files read:** {list}

```mermaid
{diagram}
```

**Nodes:** {comma-separated list of key node labels}
**Edges:** {list of "A --relation--> B" strings for grading}
```

---

## Step 2 — Rebuild graph (run in parallel with Step 1)

```bash
py CodeGrapher/run.py --feature repo --root . --dir Client_Side Server_Side test_scripts printing_information
```

Run this as a background Bash command while ground-truth agents are working.

---

## Step 3 — Skill agents query graph (after Steps 1+2 complete)

One Haiku agent per entry point. Each agent:
1. Uses **only** the graph JSON files in `CodeGrapher/graphs/` — no source reads
2. Uses the same diagram type as the ground-truth agent for that entry point
3. Queries the graph by reading tier JSON files and/or sub/ referential graphs
4. Produces the same style Mermaid diagram from graph data only

Graph file locations:
```
CodeGrapher/graphs/toc.json              ← index, always start here
CodeGrapher/graphs/tier_symbol.json      ← full symbol-level graph
CodeGrapher/graphs/sub/main_*.json       ← per-entry-point referential sub-graphs
```

Node ID format: `repo::rel/path/file.py::SymbolName`

You (orchestrator) write results to:
```
C:\Users\Mike\.claude\codegrapher-loop-workspace\iteration-2\outputs\{name}\skill_output.md
```

Same format as ground_truth.md but sourced from graph only.

---

## Step 4 — Grade (main context decision)

For each of the 5 entry points, compare ground truth vs skill output:

- **Node recall** — % of ground-truth node labels present in skill output (case-insensitive substring)
- **Edge recall** — % of ground-truth edges (A→B with relation R) present in skill output
- **Hallucination rate** — % of skill edges not present in ground truth

**Pass threshold:** node recall ≥ 0.80, edge recall ≥ 0.70, hallucination ≤ 0.15

Save to:
```
C:\Users\Mike\.claude\codegrapher-loop-workspace\iteration-2\evals\grading.json
```

```json
{
  "eval_id": "client_main",
  "diagram_type": "stateDiagram-v2",
  "node_recall": 0.0,
  "edge_recall": 0.0,
  "hallucination_rate": 0.0,
  "ground_truth_nodes": [],
  "skill_output_nodes": [],
  "missing_nodes": [],
  "missing_edges": [],
  "hallucinated_edges": [],
  "pass": false
}
```

---

## Step 5 — Fix parser gaps (if any)

If skill output is missing nodes/edges that exist in source:
1. Identify which parser is responsible (`parser_python.py` for Python)
2. Determine if the gap is a general pattern (not codebase-specific)
3. Fix the parser only if the fix is general-purpose
4. Re-run graph build and re-grade until all 5 pass

**Do not fix:**
- Gaps that only matter for this specific codebase
- Gaps in edge types the parser was never designed to emit
- False negatives that are actually correct (e.g. dynamic dispatch the parser can't statically resolve)

---

## Output structure

```
C:\Users\Mike\.claude\codegrapher-loop-workspace\iteration-2\
  ground-truth\
    client_main\ground_truth.md
    client_ui\ground_truth.md
    server_main\ground_truth.md
    server_api\ground_truth.md
    overlap_indexer\ground_truth.md
  outputs\
    client_main\skill_output.md
    client_ui\skill_output.md
    server_main\skill_output.md
    server_api\skill_output.md
    overlap_indexer\skill_output.md
  evals\
    grading.json
```
