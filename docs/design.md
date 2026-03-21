# CodeGrapher — Design Decisions

> A language-aware, build-graph-integrated codebase cartography tool.
> Designed to map data flow and structural dependencies across large, multi-language, multi-repo projects — and serve as a queryable index for AI-assisted code exploration.

---

## Problem Statement

Large codebases with interconnected repos, nested data structures, and multiple languages (C, C++, Java, Proto, XML) are difficult to reason about holistically. Loading entire files into an AI context window is wasteful and often impossible at scale. This tool generates compact, structured graph files that serve as a "table of contents" for a codebase — small enough to load selectively, rich enough to answer structural questions without reading raw source.

---

## Scope

### Phase 1 — Single feature, proven working
Parse one feature at a time. Validate output and viewer before expanding.

### Phase 2 — Multi-feature stitching
Merge per-feature graphs into a master graph. Shared types become bridge nodes between features.

### Phase 3 — MCP / AI tool integration
Expose graph query functions as an MCP server so an AI assistant can navigate large codebases by querying the graph rather than loading raw files.

---

## Supported Languages & Build Systems

| Layer | Supported (Phase 1) | Planned (Phase 2+) |
|-------|--------------------|--------------------|
| Languages | C, C++, Java, Proto, XML | Python, SQL, Postgres |
| Build systems | Makefile, Gradle | CMake |
| OS | Linux only | — |

---

## File Structure

```
codegrapher/
│
├── schema.py               # Single source of truth for node/edge types and ID rules
├── graph.py                # Core graph object: dedup, maps_to resolution, merge logic
│
├── parser_cpp.py           # C/C++ symbols, structs, includes, type usage
├── parser_proto.py         # Proto messages, fields, generates edges
├── parser_java.py          # Java classes, interfaces, imports, implements
├── parser_xml.py           # XML config structure, element keys, configures edges
├── parser_makefile.py      # Makefile targets, deps, source lists
├── parser_gradle.py        # Gradle targets and dependency chains
│
├── cc_wrapper.sh           # CC= intercept → compile_commands.json (no new tools required)
├── run.sh                  # Single entry point: runs all parsers, emits feature graph
│
├── stitch.py               # (Phase 2) Merges feature JSONs into master graph
│
├── graphs/
│   ├── toc.json            # Auto-generated repo table of contents (all features indexed)
│   └── feature_xyz.json    # One JSON per feature (the primary artifact)
│
└── viewer/
    ├── index.html
    ├── graph.js
    └── styles.css
```

**Total: ~14 files.** Each file has one clear responsibility. No redundancy.

---

## Node Identity Model

The most critical design decision. Every node has a globally unique, stable ID based on its file path and symbol name — never just the symbol name alone. This handles the case where the same function name exists in multiple files doing completely different things.

### ID Format by Node Type

| Node Type | ID Format | Example |
|-----------|-----------|---------|
| `file` | `feature::rel/path/to/file.cc` | `auth::src/login/handler.cc` |
| `symbol` | `feature::rel/path::SymbolName` | `auth::src/login/handler.cc::processToken` |
| `type` | `feature::namespace_or_pkg::TypeName` | `auth::com.example::LoginRequest` |
| `target` | `feature::buildfile_path::target_name` | `auth::Makefile::libauth.so` |
| `config` | `feature::xml_path::element.key` | `auth::res/config.xml::auth.timeout` |

### Key Rules

- **Symbol nodes are always file-scoped.** `A/B/C/D.cc::X(foo)` and `E/F/G/H.cc::X(bar)` are always two distinct nodes regardless of identical names. They are never merged.
- **Type nodes are the only shared nodes.** A proto message, C++ struct, or Java class that represents the same logical data structure across languages gets one canonical type node. This is what connects usages across files without conflating the symbols that use it.
- **`maps_to` edges link cross-language representations.** `proto::LoginRequest`, `cc::login_request_t`, and `java::LoginRequest` are three nodes all connected by `maps_to` — the same logical type in three languages.

---

## Edge Taxonomy

| Relation | Meaning | Example |
|----------|---------|---------|
| `contains` | Type A has a field of Type B (structural nesting) | `proto::Session` contains `proto::LoginRequest` |
| `maps_to` | Same logical type across languages | `proto::LoginRequest` → `cc::LoginRequest` → `java::LoginRequest` |
| `generates` | Build artifact produces this type node | `login.proto` generates `proto::LoginRequest` |
| `includes` | C/C++ file-level include | `handler.cc` includes `login.h` |
| `imports` | Java/Python import | `Handler.java` imports `com.example.Login` |
| `defines` | File defines this symbol or type | `handler.cc` defines `handler.cc::processToken` |
| `uses_type` | Symbol uses a type in its signature or body | `handler.cc::processToken` uses_type `proto::LoginRequest` |
| `calls` | Symbol calls another symbol | `handler.cc::processToken` calls `utils.cc::hashToken` |
| `depends_on` | Build target depends on another | `libauth.so` depends_on `libcrypto.a` |
| `configures` | XML config drives a symbol or target | `config.xml::auth.timeout` configures `handler.cc::processToken` |
| `implements` | Java class implements interface | `LoginHandler.java` implements `IHandler` |
| `extends` | Inheritance | `SecureHandler.java` extends `BaseHandler.java` |
| `compiles_to` | Build target produces a file | `Makefile::libauth` compiles_to `src/login/handler.cc` |
| `produces` | Symbol emits a value of this type (creates, mutates-in-place, or relays outward) | `handler.cc::processToken` produces `proto::TokenResult` |
| `consumes` | Symbol takes a value of this type as input | `handler.cc::processToken` consumes `proto::LoginRequest` |
| `typedef_of` | Type is an intra-language alias for another type | `cc::FooHandle` typedef_of `cc::Foo` |

### The `contains` / `uses_type` / `produces` / `consumes` distinction

- `contains` is a **structural** relationship between types (nesting in data definitions).
- `uses_type` is an **undirected** relationship between a symbol and a type — emitted when flow direction cannot be determined. Use `produces`/`consumes` when direction is known.
- `produces` is a **directed** relationship: this symbol emits a value of this type outward (via return or pointer mutation).
- `consumes` is a **directed** relationship: this symbol takes a value of this type as input.

This distinction matters for answering different questions:
- "What is the shape of this data?" → follow `contains` edges
- "What code touches this data?" → follow `uses_type` + `produces` + `consumes` edges
- "Where does this value come from?" → follow `produces` edges upstream, skip `relay:true` nodes
- "Where does this value go?" → follow `consumes` edges downstream

---

## C/C++ Symbol Extraction Strategy

Three-tier approach, tried in order:

1. **`compile_commands.json`** (best quality) — generated via `cc_wrapper.sh`, a thin `CC=` interceptor that logs each compiler invocation. No new tools required, works with existing Makefiles. Gives exact include paths, defines, and flags per file.
2. **clangd index** (for call graph) — once `compile_commands.json` exists, clangd builds an index in `.cache/clangd/` which provides precise cross-file call edges.
3. **Regex fallback** — for files not in `compile_commands`, or proto/XML/Java which are structurally regular enough for static parsing.

The `CC=` wrapper approach:
```makefile
make CC="codegrapher/cc_wrapper.sh gcc" CXX="codegrapher/cc_wrapper.sh g++"
```

---

## Proto Integration

- Proto files are **checked into the repo** (generated files are also in-repo, not temp directories).
- The proto parser emits `type` nodes for each message and `contains` edges for nested messages.
- `generates` edges connect the `.proto` file to each type node it defines.
- `maps_to` edges are resolved by the `graph.py` linker, which matches proto message names to their generated C++ (`.pb.h`) and Java counterparts by naming convention.

---

## Graph File Strategy

| File | Scope | Contents |
|------|-------|---------|
| `per_file/src_foo_bar.json` | One source file | All symbols, types, edges originating from that file |
| `feature_xyz.json` | One feature | Stitched rollup of all per-file graphs for the feature |
| `toc.json` | Entire repo | Auto-generated index of all features, entry points, key types |
| `master.json` | All features | (Phase 2) Full merged graph, shared types become bridge nodes |

### Why per-feature scoping matters

A per-feature graph file is small enough (typically 50–100KB) to load selectively into an AI context window. The full repo master graph may be 50MB+ and is not useful to load whole. The `toc.json` acts as a lightweight index to determine *which* feature graph to load for a given question.

### `toc.json` is auto-generated

`run.sh` scans for all `feature_*.json` files and rebuilds `toc.json` automatically after each parse run. A manual override file can add descriptions and tags per feature, which the generator merges in. No hand-authoring of the core index required.

---

## Viewer Behavior

- **Default view:** Full feature subgraph rendered as a D3 force-directed graph.
- **Entry:** Click any file node → highlights it and all direct edges, dims the rest.
- **Type expansion:** Click a type node → fans out to every file that defines or uses that type across the feature.
- **Build expansion:** Click a target node → shows its full dependency chain.
- **Sidebar:** Node details panel — file path, symbol signature, line number (where available), edge list.
- **Search:** Filters by name. Multiple matches are shown as distinct nodes (e.g., two `processToken` symbols in different files appear as two separate highlighted nodes, never merged).
- **Color coding by language layer:**
  - C/C++ → blue
  - Java → orange
  - Proto → purple
  - XML → green
  - Build targets → gray

---

## Extensibility Design

All parsers implement a common `base_parser` interface defined in `schema.py`. Adding a new language means writing one new parser file that emits the same node/edge schema. The viewer and stitcher require no changes.

### Planned language additions

| Language | New Node Types | New Edge Types |
|----------|---------------|----------------|
| Python | `py_module`, `py_class`, `py_function` | `imports`, `decorates` |
| SQL / Postgres | `table`, `column`, `view`, `stored_proc` | `references` (FK), `queries`, `mutates` |

The Python + SQL combination enables tracing from a function call in Python all the way to which database tables it reads and writes — a cross-language data flow map.

---

## MCP / AI Tool Integration (Phase 3)

The graph files are designed from the start to be queryable by an AI assistant. The MCP server wraps graph query functions over already-generated JSON files — no re-parsing at query time.

### Proposed MCP tools

| Tool | Description |
|------|-------------|
| `get_feature_summary(feature)` | Top-level map: entry points, key types, build targets |
| `expand_node(node_id)` | Direct neighbors + edge types for one node |
| `find_type(type_name)` | All representations (proto/cpp/java) + all usages |
| `trace_data_flow(from, to)` | Shortest path through the graph between two nodes |
| `get_build_chain(target)` | Full dependency tree for a build target |
| `list_features()` | Read `toc.json` — available features and their entry points |

This allows an AI to navigate a million-line codebase by querying the graph, only reading actual source file contents at the final step when a specific function body is needed.

---

## Open Questions (Deferred)

- XML structure nesting — confirm whether XML files use nested elements or flat key-value configs (impacts `contains` edge generation for XML).
- Python and SQL parser design — deferred to Phase 2.
- Master graph viewer interaction model — islands-by-default with toggle to merge, or always merged. Deferred until Phase 1 viewer is validated.

---

## Producer / Consumer Model

### Motivation

`calls` and `uses_type` describe structural relationships — A invoked B, A touches type T. They do not describe *data movement*. Two new directed edge relations capture flow direction explicitly.

### New edge relations

| Relation | Connects  | Meaning                                                                                      |
|----------|-----------|----------------------------------------------------------------------------------------------|
| `produces` | symbol → type | This symbol emits a value of this type (creates, mutates-in-place, or relays it outward) |
| `consumes` | symbol → type | This symbol takes a value of this type as input                                          |

`uses_type` is retained as the **undirected fallback** — emitted when direction cannot be determined. When direction is known, emit `produces` / `consumes` instead. They are directed refinements of `uses_type`, not replacements.

### Edge metadata fields

Two fields added to the `produces` edge:

| Field | Values | Meaning |
| --- | --- | --- |
| `via` | `return_value`, `param_mutation` | How the value leaves the function — explicit return type vs mutation of a non-const pointer parameter (void function "return") |
| `relay` | `true`, `false` | If `true`, the symbol did not originate this value — it received it from upstream and forwarded it. Agents must keep walking upstream to find the true origin. |

One field added to the `consumes` edge:

| Field  | Values             | Meaning                                                                                                                                                    |
|--------|--------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `role` | `data`, `control`  | `data` — the input's content appears in the output. `control` — the input shapes behavior but its data does not flow into the output (e.g. a config or policy struct consulted for decisions). |

### Inference rules (from signatures, no body analysis required)

| Signature pattern                                                     | Edge emitted                                  |
|-----------------------------------------------------------------------|-----------------------------------------------|
| Return type `T*` or `T`                                               | `produces → T` with `via: return_value`       |
| Non-const pointer parameter `T*`                                      | `produces → T` with `via: param_mutation`     |
| `const T*` or `const T&` parameter                                    | `consumes → T` with `role: data`              |
| `T` by value parameter                                                | `consumes → T` with `role: data`              |
| Same type in both input parameter and return                          | `produces` with `relay: true`                 |
| Config/policy type as `const T*` where T is a proto or config type   | `consumes → T` with `role: control`           |
| Direction not determinable                                            | `uses_type` (undirected fallback)             |

### The relay pattern

When a function receives a value, does work, and passes the same value onward — it is a **relay**. The `relay: true` flag on the `produces` edge tells agents not to treat this symbol as the origin of the value. Example:

```text
B --produces (relay:true)--> FooStruct    ← B is passing it through, not creating it
C --consumes--> FooStruct
C --produces (via:param_mutation)--> FooStruct    ← C mutates in place (void function)
B --consumes--> FooStruct                ← B reads the post-mutation result
```

An agent tracing "where does FooStruct originate?" will skip relay nodes and continue upstream.

### Intra-function sequencing

Signature-level inference covers ~80% of cases. It cannot determine the *order* of operations within a function body — e.g. whether B reads FooStruct before or after calling C.

This information is available from compiler IR without writing a custom analyzer:

| Toolchain  | Source of sequencing data                                                         |
|------------|-----------------------------------------------------------------------------------|
| clang/LLVM | LLVM IR (`clang -emit-llvm`), SSA form names pre/post-call values explicitly      |
| clangd     | AST index already built for IDE features — queryable for CFG                      |
| Python     | `dis` (bytecode) or `ast` (stdlib)                                                |
| Java       | Bytecode via `javap` or compiler API                                              |

**Design boundary:** Signature inference is the baseline and runs on any file without a build system. Compiler IR query is an optional enrichment pass that fills in sequencing detail the signature cannot provide. Both emit the same schema — `produces`/`consumes` with the same metadata fields. The source of inference is an implementation detail of the parser, not the schema.

### Relationship to cross-language flow

`produces`/`consumes` edges connect symbols to type nodes. Type nodes are already shared across languages via `maps_to` edges. This means a data flow chain can cross language boundaries naturally:

```text
B.cc  --produces--> FooStruct
      (maps_to)
      FooStruct <--generates-- D.proto
C.cc  --consumes (role:control)--> ProtoConfig
C.cc  --produces (via:param_mutation)--> FooStruct
```

An agent can trace data flow from a C++ function through a proto-defined type without any special cross-language handling — the type node is the bridge.

### Pointer depth on `contains` edges

Add `ptr_depth: int` (default 0) to `contains` edges:

- `ptr_depth: 0` — direct field (`Bar bar`)
- `ptr_depth: 1` — pointer field (`Bar* bar`)
- `ptr_depth: 2` — pointer-to-pointer (`Bar** bar`)

This allows reconstruction of the full dereference chain:

```text
FooHandle** → FooHandle* → Foo → Bar → Baz
```

as a typed chain with dereference counts at each step. Pointer depth is structural metadata — it does not change the `contains` relationship, only how many dereferences are required to reach the nested type.

### typedef chains

Typedef aliases and opaque handle patterns require a `typedef_of` edge (symbol → type) to remain traversable. Without it, `FooHandle` is a dead end — the graph cannot chase it to the underlying struct definition.

| Relation      | Meaning                                                        |
|---------------|----------------------------------------------------------------|
| `typedef_of`  | This type is an alias for another type (within one language)   |

This is distinct from `maps_to` (which crosses languages) — `typedef_of` is intra-language aliasing.
