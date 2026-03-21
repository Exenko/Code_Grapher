# CodeGrapher Eval Design

## Purpose

Measure how accurately the MCP server tools allow an agent to reconstruct the data-flow
diagram for a subsystem — compared to an agent that reads the source files directly.

This tests whether CodeGrapher's semantic layer (produces/consumes edges, relay flags,
type nodes, maps_to bridges) is actually useful for LLM-driven code understanding.

---

## Eval mechanism: two-agent comparison

For each eval case, spawn two agents in the same turn:

### Agent A — Ground truth agent
- Task: Read the relevant source files directly (no MCP tools).
- Produce a Mermaid `flowchart LR` data-flow diagram for the specified sub-system.
- Include nodes for: entry point function, key symbols in the call chain, data types produced/consumed.
- Include edges labeled with the relation type: `-->|produces|`, `-->|consumes|`, `-->|calls|`.
- Save diagram to `outputs/ground_truth.md`.

### Agent B — Skill agent
- Task: Use **only** `mcp_server.py` tools to explore the graph. Do NOT read source files.
- Available tools: `list_entry_points`, `get_feature_summary`, `expand_node`, `find_type`, `trace_data_flow`
- Produce the same Mermaid `flowchart LR` diagram from tool output alone.
- Save diagram to `outputs/skill_output.md`.
- Also save the tool call log to `outputs/tool_calls.json` — one entry per call with `{tool, args, summary_of_result}`.

The MCP server must be running at: `py CodeGrapher/mcp_server.py --graphs CodeGrapher/graphs`

---

## Metrics (3)

**1. Node recall** — % of ground-truth nodes present in skill output
- A node counts as present if its label appears in the skill Mermaid output (case-insensitive substring match is fine)

**2. Edge recall** — % of ground-truth edges (A→B with relation R) present in skill output
- An edge counts as present if both endpoints appear AND the relation label matches

**3. Hallucination rate** — % of skill-output edges that do NOT exist in ground truth
- Measures invented connections that aren't in the actual code

Target baseline: node recall ≥ 0.80, edge recall ≥ 0.70, hallucination ≤ 0.15.

---

## Eval set: stress-test (Phase 3 scope)

All three cases use the stress-test codebase: `CodeGrapherStressTest/`.
Ground truth is in `CodeGrapherStressTest/GROUND_TRUTH.md` (sections 3.5 and 3.6).

### eval-broker
**Scope:** Broker sub-system data flow
**Entry point:** `broker/main.cc` → broker FSM
**Key chain:** `on_msg_received → inspect_header → lookup_route → forward_message → dispatch_event`
**Key types:** `Header`, `RoutingKey`, `Session`
**Special feature to test:** `relay:true` on all broker produces edges; XML routing config (role:control)
**Ground truth section:** GROUND_TRUTH.md §3.5 "Broker (depth 4)"

### eval-consumer
**Scope:** Consumer sub-system data flow
**Entry point:** `consumer/main.cc` → consumer FSM
**Key chain:** `on_msg_received → detect_format → decode_message → process_payload → validate → transform → dispatch_event`
**Key types:** `Envelope`, `MessageBody`, `LegacyEvent_Proto`, `LegacyEvent_WSDL`
**Special feature to test:** depth-6 cap handling; proto vs WSDL decoder branch; maps_to bridge
**Ground truth section:** GROUND_TRUTH.md §3.5 "Consumer (depth 6)" + §3.6 type relationships

### eval-producer
**Scope:** Producer sub-system data flow
**Entry point:** `producer/main.cc` → producer FSM
**Key chain:** `trigger_event → encode_payload → select_serializer → serialize_proto/serialize_wsdl → transmit_message → dispatch_event`
**Key types:** `RawBytes`, `MessageBody`, `Payload`, `PayloadHandle`, `PayloadHandlePP` (typedef chain), `Envelope`
**Special feature to test:** typedef chain (ptr_depth 0-3); proto path vs legacy WSDL path split
**Ground truth section:** GROUND_TRUTH.md §3.5 "Producer (depth 5)" + §3.2 typedef chain

---

## MCP tool usage guide for skill agent

```
# Step 1: Get oriented
list_entry_points()                    # see all 3 entry points
get_feature_summary()                  # node counts, file list

# Step 2: Find the entry point node
# Entry point IDs follow: stress::path/file.cc::SymbolName
expand_node("stress::producer/main.cc::main")

# Step 3: Follow call/produces/consumes chains
expand_node("<node_id>")               # see all outgoing + incoming edges

# Step 4: Resolve types
find_type("MessageBody")               # producers, consumers, typedef chain
find_type("EventBus")                  # cross-service shared type

# Step 5: Trace full data flow path
trace_data_flow({
  "start": "stress::producer/main.cc::main",
  "end":   "stress::consumer/output.cc::dispatch_event",
  "algorithm": "data_flow"             # default: BFS over produces/consumes/calls
})
```

---

## Grading

After both agents complete:

1. Parse the Mermaid diagrams to extract node labels and edges
2. Compute the 3 metrics above
3. Save to `grading.json`:

```json
{
  "eval_id": "eval-broker",
  "node_recall": 0.87,
  "edge_recall": 0.75,
  "hallucination_rate": 0.08,
  "ground_truth_nodes": ["on_msg_received", "inspect_header", ...],
  "skill_output_nodes": ["on_msg_received", ...],
  "missing_nodes": [...],
  "missing_edges": [...],
  "hallucinated_edges": [...]
}
```

---

## Future eval set (Phase 4+)

Once stress-test evals are solid, expand to the SmartRecipeApp Python codebase:
- `Client_Side/` — autofill engine, meal planning, preference compiler
- `Server_Side/` — Flask API, database layer
- `test_scripts/` — integration tests

These require the ground-truth agent to produce diagrams from scratch (no pre-made GROUND_TRUTH.md).
Start with stress-test; add Python evals in a later iteration.
