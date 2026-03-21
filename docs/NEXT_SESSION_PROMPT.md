# CodeGrapher — Next Session Operating Procedure

## Step 1: Read the handoff first

Before doing anything else, read `CodeGrapher/HANDOFF_PRODUCER_CONSUMER.md` in full.
It contains the current state of every component, what was verified, what was not, and what is open.
Do not rely on memory or this file alone — the handoff is the ground truth.

---

## Ground rules (enforce for every session, no exceptions)

### CodeGrapher is language-agnostic and project-agnostic

This is the single most important invariant. CodeGrapher must work equally well on any codebase.

Prohibited in any `CodeGrapher/` source file (`*.py`, `*.js`, `*.html`, `*.md` that drives logic):
- Hardcoded paths: no `Client_Side`, `Server_Side`, `test_scripts`, or any path specific to SmartRecipeApp
- Hardcoded names: no `autofill_engine`, `SmartRecipe`, `household`, or any symbol specific to SmartRecipeApp
- Hardcoded patterns: no detection logic whose thresholds or heuristics were tuned to pass on SmartRecipeApp specifically

The SmartRecipeApp repository is only the test bed. Every fix must be justified by general correctness, not by "it works on this repo."

If a heuristic must exist (e.g., entry point detection), it must be expressed as a configurable rule or a documented general principle, not a magic list of project-specific strings.

### No new files without explicit agreement

Before creating any new file, state what the file will be, why it cannot be added to an existing file, and wait for the user to agree. This applies to source files, test files, and documentation files alike.

### Sub-agents for all exploration and implementation

Use Haiku sub-agents for:
- Reading and exploring files
- Running commands and inspecting output
- Writing or editing code

Use the main context (Claude Sonnet) for:
- Deciding what to do and why
- Evaluating whether a proposed fix is general vs. project-specific
- Making architectural decisions
- Reviewing sub-agent output before accepting it

Do not run Bash commands or read files directly from the main context unless the output is short and the intent is critical-path decision-making.

---

## Refinement loop (follow this every session)

Each session should iterate through this loop at least once:

1. **Build the graph** against the current test codebase (see checklist below).
2. **Inspect the output** — look at `tier_symbol.json`, `toc.json`, sub-graphs, and `analyze/` output. Identify what looks wrong, incomplete, or suspiciously project-specific.
3. **Diagnose the root cause** — is the problem in the parser, the builder, the analyzer, or the schema? Is the fix general or a patch for SmartRecipeApp specifically?
4. **Fix the underlying logic** so it is more correct in general. Do not patch symptoms.
5. **Re-run and compare** — rebuild the graph and verify the fix improved the output. Check that counts and shapes are plausible (not inflated, not empty).
6. **Update the handoff** — before ending the session, rewrite the relevant sections of `HANDOFF_PRODUCER_CONSUMER.md` to reflect current state. Mark items as done, partially done, or open with updated notes.

---

## Open problems in priority order

1. **Browser smoke test**: Start LOD server, open browser, verify: (a) edge colors are correct by relation type, (b) relay edges are dashed, (c) control edges are violet, (d) clicking a node and pressing "Data Flow Trace" shows the trace layout
2. **Type display quality**: Methods are currently included in type expansion alongside fields (both are `contains` children). Consider filtering `_collect_fields` to exclude methods (labels with a dot AND more than one dot component that match the class methods pattern)
3. **Larger graph test**: Run against the full repo (`--dir Client_Side Server_Side`) and check LOD server performance with per-file sub-graph loading

---

## Primary use cases (keep these in mind for every decision)

**Human use:** A developer wants to visually trace how a feature works across many files without reading all the code. They need a diagram that shows the execution path and the type structure — not a hairball of every edge in the codebase.

**LLM use:** An LLM agent calls CodeGrapher to get a compact structured map of a feature and loads it into context instead of raw source files. The output must be token-efficient, structured, and machine-readable.

Every design decision should be evaluated against both use cases. If a change makes the output larger without making it more informative, reconsider it.

---

## Target output format

The primary output targets are:

- **`stateDiagram-v2`** (Mermaid) — execution flow: which function calls which, in what order, across which files
- **`classDiagram`** (Mermaid) — type structure: which type contains which fields, with pointer depth

These are the outputs that serve both use cases above.

The force graph viewer (`viewer/graph.js`, served by `serve.py`) is secondary and legacy. It is useful for exploration but is not the primary deliverable. Do not let viewer work crowd out analysis output quality.

When `analyze/flow_trace.py` or `analyze/type_expander.py` produce Mermaid output, that is the canonical output for the feature. Viewer rendering is a bonus.

---

## Testing checklist (start of each session)

1. Rebuild: `py CodeGrapher/run.py --feature autofill --root . --dir Client_Side/utils Client_Side/first_boot`
2. Verify flow trace: `--analyze flow --entry Client_Side/utils/autofill_engine.py` → entry should be `run_autofill_pipeline`
3. Verify type expansion: `--analyze type --type CookingSession` → should show all 8 fields with type annotations
4. Start LOD server: `py CodeGrapher/serve.py --graphs CodeGrapher/graphs` → open browser, zoom in, verify edge colors and per-file symbol loading
5. Project-specificity grep: all hits must be in comments/docstrings only
6. Update handoff at session end
