# Broker Data-Flow Diagram (Ground Truth)

## Source files read

- `CodeGrapherStressTest/broker/main.cc`
- `CodeGrapherStressTest/broker/relay.h`
- `CodeGrapherStressTest/broker/relay.cc`
- `CodeGrapherStressTest/broker/router.h`
- `CodeGrapherStressTest/broker/router.cc`
- `CodeGrapherStressTest/config/broker_config.xml`
- `CodeGrapherStressTest/GROUND_TRUTH.md` (sections 3.4, 3.5)

## Diagram

```mermaid
flowchart LR
    subgraph BrokerChain ["Broker Call Chain (depth 4)"]
        on_msg_received["on_msg_received (relay.cc)"]
        inspect_header["inspect_header (router.cc)"]
        lookup_route["lookup_route (router.cc)"]
        forward_message["forward_message (relay.cc)"]
        dispatch_event_broker["dispatch_event (relay.cc)"]

        on_msg_received -->|calls| inspect_header
        inspect_header -->|calls| lookup_route
        lookup_route -->|calls| forward_message
        forward_message -->|calls| dispatch_event_broker
    end

    subgraph DataTypes ["Data Types & Control Inputs"]
        Header["Header (proto/messages.proto) contains RoutingKey"]
        RoutingKey["RoutingKey (router.h) destination, priority, flags"]
        Session["Session (relay.h) contains Header"]
        RawBytes["RawBytes (relay.h) uint8_t* data, size_t len"]
        BrokerConfig["broker_config.xml (config/) RoutingTable"]
        EventBus["EventBus (producer/types.h) publish()"]
    end

    on_msg_received -->|consumes| RawBytes
    on_msg_received -->|consumes| Session
    inspect_header -->|produces| RoutingKey
    inspect_header -->|consumes| RawBytes
    lookup_route -->|consumes| RoutingKey
    lookup_route -->|consumes| BrokerConfig
    lookup_route -->|produces| Header
    forward_message -->|consumes| RawBytes
    forward_message -->|"relay:true"| Header
    dispatch_event_broker -->|consumes| RawBytes
    dispatch_event_broker -->|calls| EventBus

    Session -->|contains| Header
    Header -->|contains| RoutingKey
```

## Key Observations

1. **Call Chain Depth (4 hops)**: on_msg_received → inspect_header → lookup_route → forward_message → dispatch_event

2. **Relay Behavior**: All `produces` edges from the Broker are annotated `relay:true`. The broker never originates data — it only inspects the upstream message header, consults the XML routing table (role:control), and forwards the original RawBytes downstream.

3. **XML Config as Control Input**: `broker_config.xml` is consumed by `lookup_route()` via RoutingTable. It does NOT flow into the forwarded message payload — only shapes routing logic (role:control).

4. **EventBus Bridge**: `dispatch_event()` is the local Broker wrapper calling into the shared `EventBus::publish()` type. All three services' dispatch_event wrappers converge on this single type node.

5. **Type Relationships Across File Boundaries**: Header (proto/messages.proto) and RoutingKey (broker/router.h) form a cross-file contains edge. Session (broker/relay.h) also contains Header.

6. **Intentional Tracing Stress**: Three distinct dispatch_event symbol nodes (producer, broker, consumer) all call the same EventBus type node. Broker and Consumer produces edges should be relay:true.
