# Consumer Data-Flow Diagram (Skill Output)

Produced by querying CodeGrapher/graphs/feature_stress.json directly (graph query proxy for MCP tools).

## Diagram

```mermaid
flowchart LR
    subgraph CONSUMER["Consumer Sub-system"]
        main_c["main\n(consumer/main.cc)"]
        fsm_init_c["consumer_fsm_init"]
        fsm_run_c["consumer_fsm_run"]
        wait["consumer_handle_waiting"]
        on_msg_c["on_msg_received"]
        decoding["consumer_handle_decoding"]
        detect["detect_format"]
        decode_msg["decode_message"]
        decode_p["decode_proto"]
        decode_w["decode_wsdl"]
        processing["consumer_handle_processing"]
        proc_payload["process_payload"]
        validate["validate"]
        transform["transform"]
        enrich["enrich"]
        writing["consumer_handle_writing"]
        write_out["write_output"]
        dispatch_c["dispatch_event"]
        on_err["consumer_on_error"]
        sub_all["consumer_subscribe_all"]
    end

    subgraph TYPES_C["Consumer Types"]
        WireFormat["WireFormat\n(type/enum)"]
        DecodedMessage["DecodedMessage\n(type)"]
        ProcessedPayload["ProcessedPayload\n(type)"]
        ConsumerFSM["ConsumerFSM\n(type)"]
        RawBytes_c["RawBytes\n(type)"]
        EventBus_c["EventBus\n(type)"]
    end

    main_c -->|calls| fsm_init_c
    main_c -->|calls| fsm_run_c

    fsm_init_c -->|produces| ConsumerFSM
    fsm_init_c -->|produces| EventBus_c
    fsm_init_c -->|calls| sub_all

    sub_all -->|produces| EventBus_c
    sub_all -->|consumes| EventBus_c

    fsm_run_c -->|calls| wait
    fsm_run_c -->|calls| processing
    fsm_run_c -->|calls| writing
    fsm_run_c -->|calls| on_err["consumer_handle_error"]

    wait -->|produces| ConsumerFSM
    wait -->|consumes| ConsumerFSM
    on_msg_c -->|produces| RawBytes_c
    on_msg_c -->|consumes| RawBytes_c
    on_msg_c -->|produces| ConsumerFSM
    on_msg_c -->|consumes| ConsumerFSM
    on_msg_c -->|calls| decoding

    decoding -->|calls| detect
    decoding -->|calls| decode_msg
    decoding -->|calls| dispatch_c
    decoding -->|calls| processing

    detect -->|produces| WireFormat
    detect -->|consumes| RawBytes_c

    decode_msg -->|produces| DecodedMessage
    decode_msg -->|consumes| RawBytes_c
    decode_msg -->|consumes| WireFormat
    decode_msg -->|calls| decode_p
    decode_msg -->|calls| decode_w

    decode_p -->|produces| DecodedMessage
    decode_p -->|consumes| RawBytes_c

    decode_w -->|produces| DecodedMessage
    decode_w -->|consumes| RawBytes_c

    processing -->|calls| proc_payload
    processing -->|calls| dispatch_c
    processing -->|calls| writing

    proc_payload -->|produces| ProcessedPayload
    proc_payload -->|produces| DecodedMessage
    proc_payload -->|consumes| DecodedMessage
    proc_payload -->|calls| validate
    proc_payload -->|calls| transform
    proc_payload -->|calls| enrich

    validate -->|consumes| DecodedMessage
    transform -->|produces| ProcessedPayload
    transform -->|produces| DecodedMessage
    transform -->|consumes| DecodedMessage
    enrich -->|produces| ProcessedPayload
    enrich -->|consumes| ProcessedPayload

    writing -->|calls| write_out
    writing -->|calls| dispatch_c

    write_out -->|consumes| ProcessedPayload
    write_out -->|calls| dispatch_c

    dispatch_c -->|produces| RawBytes_c
    dispatch_c -->|consumes| RawBytes_c
    dispatch_c -->|calls| EventBus_c

    on_err -->|calls| dispatch_c
```

## Observations

- **Full 6-hop chain captured**: on_msg_received → consumer_handle_decoding → detect_format/decode_message → consumer_handle_processing → process_payload → consumer_handle_writing → write_output → dispatch_event(WRITE_COMPLETE)
- **Proto/WSDL branch**: decode_message calls both decode_proto and decode_wsdl. detect_format produces WireFormat which decode_message consumes to dispatch correctly.
- **Sub-FSM chain**: process_payload calls validate → transform → enrich. transform and enrich produce/consume ProcessedPayload in sequence.
- **dispatch_event → EventBus**: Consumer's dispatch_event has a `calls` edge to EventBus, same pattern as broker and producer.
- **maps_to gap**: The graph does NOT show LegacyEvent_Proto or LegacyEvent_WSDL as consumer-side types. The maps_to edges for LegacyEvent exist at the producer/proto level but consumer decoder only sees RawBytes → DecodedMessage. This is a gap in what the graph exposes for consumer eval.

## Gap analysis

- LegacyEvent maps_to bridge is NOT directly visible from consumer-side graph data — it would require cross-subsystem type tracing (find_type("LegacyEvent") across all nodes).
- consumer_handle_decoding also has a `calls dispatch_event` edge for error cases (bad_format → ERROR state), which is captured.
- The graph captures `on_msg_received` in consumer/state_machine.cc (not decoder.cc) — it's the FSM handler, not the decoder entry.
