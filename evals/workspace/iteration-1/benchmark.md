# CodeGrapher Eval Benchmark — Iteration 1

**Skill:** codegrapher-loop
**Date:** 2026-03-17
**Method:** Skill agent queries feature_stress.json (graph query proxy for MCP tools) vs ground-truth agent reading source files directly.

## Results Summary

| Eval | Assertions Passed | Pass Rate | Key Strength | Key Gap |
|---|---|---|---|---|
| eval-broker | 5/5 | **100%** | Full 4-hop chain + relay pattern inference + EventBus | relay:true not a graph edge attribute — inferred from symmetric produce+consume |
| eval-consumer | 5/5 | **100%** | Full 6-hop chain + decoder branch + sub-FSM chain | maps_to LegacyEvent bridge not visible from consumer-side graph alone |
| eval-producer | 5/5 | **100%** | Full typedef chain (5 nodes) + both serializer paths + maps_to | Envelope requires cross-file type tracing (defined in proto/, not producer/) |

**Aggregate pass rate: 100% (15/15 assertions)**

## Qualitative Analysis

### What the graph captures well

1. **Call chains** — all internal call sequences (4-hop broker, 6-hop consumer, 5-hop producer) are fully represented via `calls` edges. The graph is the primary value-add here.

2. **Type nodes and data flow** — `produces`/`consumes` edges correctly link symbols to types (RawBytes, DecodedMessage, ProcessedPayload, RoutingKey, Session, etc.). An agent can reconstruct the full data-flow picture.

3. **Typedef chain** — All 4 `typedef_of` edges (MessageBody→RawBytes, Payload→MessageBody, PayloadHandle→Payload, PayloadHandlePP→PayloadHandle) are present. Chain order correctly implies ptr_depth.

4. **maps_to bridge (producer side)** — LegacyEvent_CC → LegacyEvent_Proto → LegacyEvent_WSDL cross-format mapping is captured and findable via cross-subsystem type query.

5. **EventBus convergence** — All 3 service `dispatch_event` symbols have `calls` edges to the shared EventBus type node. The 3→1 convergence pattern is intact.

6. **XML config as control input** — broker_config.xml defines RoutingTable, which lookup_route consumes. Role as control-type input is inferrable.

### Parser gaps to fix

| Priority | Gap | Fix |
|---|---|---|
| High | `relay:true` not on broker edges | Emit `relay` boolean on `produces` edges for broker/relay.cc nodes |
| Medium | `select_serializer` missing call edges to serializer functions | Parse the conditional dispatch in encoder.cc and emit calls edges |
| Medium | `ptr_depth` not on `typedef_of` edges | Add ptr_depth attribute when emitting typedef_of edges in parser_cpp.py |
| Low | `maps_to` bridge not cross-linked to consumer decoder | Add uses_type or maps_to edge from decode_wsdl to LegacyEvent types |

### Eval assertion improvements for iteration 2

1. **eval-broker**: Add explicit assertion for relay:true annotation or relay pattern inference
2. **eval-consumer**: Strengthen maps_to assertion to check diagram body (not observations text); add sub-FSM chain assertion (validate → transform → enrich)
3. **eval-producer**: Add LegacyEvent_CC/maps_to assertion; add ptr_depth check (expected to fail — useful regression test)

## Decision

**No skill iteration needed** — all assertions pass and the skill correctly guides an agent to the right outputs. The gaps are parser-level issues (not skill-level), which should be addressed in parser fixes and re-evaluated.

**Recommended next step:** Fix the 4 parser gaps above, rebuild the stress graph, and run iteration 2 to verify improvements.
