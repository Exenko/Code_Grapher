# Broker Data-Flow Diagram (Skill Output)

Produced by querying CodeGrapher/graphs/feature_stress.json directly (graph query proxy for MCP tools).

## Diagram

```mermaid
flowchart LR
    subgraph BROKER["Broker Sub-system"]
        main_b["main\n(broker/main.cc)"]
        fsm_init["broker_fsm_init"]
        fsm_run["broker_fsm_run"]
        listen["broker_handle_listening"]
        routing["broker_handle_routing"]
        forwarding["broker_handle_forwarding"]
        err_rec["broker_handle_error_recovery"]
        on_msg["on_msg_received"]
        inspect["inspect_header"]
        lookup["lookup_route"]
        fwd_msg["forward_message"]
        dispatch["dispatch_event"]
        load_rt["load_routing_table"]
    end

    subgraph TYPES_B["Broker Types"]
        Session["Session\n(type)"]
        RoutingKey["RoutingKey\n(type)"]
        RoutingTable["RoutingTable\n(type)"]
        BrokerFSM["BrokerFSM\n(type)"]
        RawBytes_b["RawBytes\n(type)"]
        EventBus["EventBus\n(type)"]
    end

    subgraph CONFIG["Config (role:control)"]
        broker_cfg["broker_config.xml\nRoutingTable / RetryPolicy / ErrorRecovery"]
    end

    main_b -->|calls| fsm_init
    main_b -->|calls| fsm_run

    fsm_init -->|produces| BrokerFSM
    fsm_init -->|produces| EventBus
    fsm_init -->|calls| broker_subscribe_all["broker_subscribe_all"]

    fsm_run -->|calls| listen
    fsm_run -->|calls| routing
    fsm_run -->|calls| inspect
    fsm_run -->|calls| lookup
    fsm_run -->|calls| forwarding
    fsm_run -->|calls| err_rec

    listen -->|calls| on_msg
    listen -->|produces| RawBytes_b
    listen -->|consumes| RawBytes_b

    on_msg -->|produces| RawBytes_b
    on_msg -->|consumes| RawBytes_b
    on_msg -->|produces| Session
    on_msg -->|consumes| Session
    on_msg -->|calls| inspect
    on_msg -->|calls| lookup
    on_msg -->|calls| fwd_msg
    on_msg -->|calls| dispatch

    inspect -->|produces| RoutingKey
    lookup -->|consumes| RoutingKey
    lookup -->|consumes| RoutingTable

    load_rt -->|produces| RoutingTable
    broker_cfg -->|defines| RoutingTable

    forwarding -->|calls| fwd_msg
    forwarding -->|calls| dispatch
    forwarding -->|calls| session_destroy["session_destroy"]

    fwd_msg -->|produces| RawBytes_b
    fwd_msg -->|consumes| RawBytes_b

    dispatch -->|produces| RawBytes_b
    dispatch -->|consumes| RawBytes_b
    dispatch -->|calls| EventBus

    err_rec -->|calls| dispatch
    err_rec -->|calls| fwd_msg

    broker_subscribe_all -->|produces| EventBus
    broker_subscribe_all -->|consumes| EventBus
```

## Observations

- **relay:true pattern detected**: All broker state handlers (listening, routing, forwarding, error_recovery) both produce AND consume RawBytes — indicating pass-through / relay behavior. The graph captures this as symmetric produces+consumes on the same type, which maps to the relay:true semantic.
- **Control-role config**: broker_config.xml defines RoutingTable, which is consumed by lookup_route — this is the XML routing table as a control-role input.
- **EventBus bridge**: dispatch_event has a direct `calls` edge to EventBus type, correctly capturing the cross-service notification channel.
- **Session lifecycle**: session_create/session_destroy produce/consume Session type; Session.header uses_type Header (cross-file boundary from router.h).
- **inspect_header → RoutingKey → lookup_route**: The data-flow chain through inspect_header producing RoutingKey and lookup_route consuming it is clearly captured.

## Gap analysis

- The graph does NOT expose a `relay:true` boolean flag on edges directly — it encodes relay semantics via symmetric produces+consumes. An MCP tool agent would need to infer relay from this pattern.
- `inspect_header` appears in call chains from both `on_msg_received` and `broker_fsm_run` (duplicated because defined in both .h and .cc).
- `Header` type (from router.h) appears in Session.header via uses_type but is not a standalone broker-defined type — it comes from proto/messages.proto.
