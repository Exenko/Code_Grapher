# Producer Data-Flow Diagram (Skill Output)

Produced by querying CodeGrapher/graphs/feature_stress.json directly (graph query proxy for MCP tools).

## Diagram

```mermaid
flowchart LR
    subgraph init["FSM Initialization"]
        main["main()"]
        fsm_init["producer_fsm_init()"]
        config["ProducerConfig"]
        bus["EventBus*"]
        subsc["subscribe_all()"]
    end

    subgraph fsm["State Machine Loop"]
        idle_h["handle_idle()"]
        enc_h["handle_encoding()"]
        tx_h["handle_transmitting()"]
        ack_h["handle_waiting_ack()"]
        err_h["handle_error()"]
    end

    subgraph enc_pipe["Encoding Pipeline"]
        enc_pay["encode_payload()"]
        sel_ser["select_serializer()"]
        ser_proto["serialize_proto()"]
        ser_wsdl["serialize_wsdl() (legacy)"]
        transmit["transmit_message()"]
    end

    subgraph types["Type Chain (typedef_of)"]
        raw["RawBytes"]
        msg_body["MessageBody (ptr_depth=0)"]
        payload["Payload (ptr_depth=1)"]
        handle["PayloadHandle (ptr_depth=2)"]
        handle_pp["PayloadHandlePP (ptr_depth=3)"]
    end

    subgraph events["Event Triggers"]
        trigger["trigger_event()"]
        ack_ev["ack_received_event()"]
        timeout_ev["timeout_event()"]
        error_ev["error_event()"]
    end

    subgraph callbacks["Callbacks"]
        dispatch["dispatch_event()"]
        on_state["on_state_change()"]
        register["register_callbacks()"]
    end

    subgraph legacy["Legacy Encoder"]
        build_leg["build_legacy_event()"]
        leg_event["LegacyEvent_CC"]
    end

    main -->|calls| fsm_init
    fsm_init -->|produces| config
    fsm_init -->|produces| bus
    fsm_init -->|calls| subsc
    fsm_init -->|calls| register

    idle_h -->|calls| trigger
    enc_h -->|calls| enc_pay
    enc_pay -->|calls| sel_ser
    enc_pay -->|calls| ser_proto
    enc_pay -->|calls| transmit
    enc_pay -->|calls| dispatch

    sel_ser -->|proto path| ser_proto
    sel_ser -->|legacy path| ser_wsdl

    tx_h -->|calls| build_leg
    tx_h -->|calls| ser_wsdl
    build_leg -->|produces| leg_event
    ser_wsdl -->|consumes| leg_event

    msg_body -->|"typedef_of ptr_depth=0"| raw
    payload -->|"typedef_of ptr_depth=1"| msg_body
    handle -->|"typedef_of ptr_depth=2"| payload
    handle_pp -->|"typedef_of ptr_depth=3"| handle

    trigger -->|calls| dispatch
    ack_h -->|calls| ack_ev
    ack_h -->|calls| timeout_ev
    err_h -->|calls| error_ev
    error_ev -->|calls| dispatch

    dispatch -->|produces| bus
    on_state -->|produces| bus
    register -->|consumes| bus
    transmit -->|calls| dispatch
```

## Observations

### Typedef chain — ptr_depth IS stored on edges
The graph stores `ptr_depth` as a field on `typedef_of` edges: 0, 1, 2, 3. The chain is:
- RawBytes (base struct)
- MessageBody ← typedef_of RawBytes, ptr_depth=0
- Payload ← typedef_of MessageBody, ptr_depth=1
- PayloadHandle ← typedef_of Payload, ptr_depth=2
- PayloadHandlePP ← typedef_of PayloadHandle, ptr_depth=3

### Dual-path serialization
- Proto path: encode_payload → select_serializer → serialize_proto → produces Envelope
- Legacy path: handle_transmitting → build_legacy_event → produces LegacyEvent_CC → serialize_wsdl

### select_serializer branching
select_serializer checks ProducerConfig.use_proto. The graph shows it calling serialize_proto and serialize_wsdl (both branches encoded as calls edges).

### EventBus integration
18+ edges from producer components reference EventBus. dispatch_event, on_state_change, register_callbacks, subscribe_all all interact with it.

### relay field
NOT present on producer edges — correctly absent (relay:true only applies to broker).

## Gap analysis
- Envelope is defined in proto/messages.proto (not producer files) — requires cross-file type tracing to find
- EventEnvelope references unresolved EventType (external definition)
