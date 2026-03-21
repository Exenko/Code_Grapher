#include "state_machine.h"
#include "encoder.h"
#include "legacy_encoder.h"
#include "callbacks.h"
#include "types.h"
#include <stdlib.h>

void producer_fsm_init(ProducerFSM* fsm, EventBus* bus, const ProducerConfig* cfg) {
    fsm->state        = P_IDLE;
    fsm->bus          = bus;
    fsm->config       = *cfg;
    fsm->ack_received = 0;
    fsm->retry_count  = 0;
    subscribe_all(bus);
}

void producer_fsm_run(ProducerFSM* fsm) {
    while (fsm->state != P_FATAL) {
        switch (fsm->state) {
            case P_IDLE:         handle_idle(fsm);         break;
            case P_ENCODING:     handle_encoding(fsm);     break;
            case P_TRANSMITTING: handle_transmitting(fsm); break;
            case P_WAITING_ACK:  handle_waiting_ack(fsm);  break;
            case P_ERROR:        handle_error(fsm);        break;
            default: break;
        }
    }
}

// IDLE: wait for external trigger
void handle_idle(ProducerFSM* fsm) {
    // blocks until trigger_event() is called externally
    fsm->state = P_ENCODING;
}

// ENCODING: branch on config flag
void handle_encoding(ProducerFSM* fsm) {
    if (fsm->config.use_proto) {
        fsm->encoding_path = PATH_PROTO;
        // proto path: encode_payload called in handle_transmitting
    } else {
        fsm->encoding_path = PATH_LEGACY_WSDL;
        // legacy path: build_legacy_event + serialize_wsdl called in handle_transmitting
    }
    fsm->state = P_TRANSMITTING;
}

// TRANSMITTING: encode and send
// This is where the 5-hop internal call chain fires:
// encode_payload → select_serializer → serialize_proto → transmit_message → dispatch_event
void handle_transmitting(ProducerFSM* fsm) {
    PayloadHandlePP src = NULL; /* would come from data source */
    RawBytes* out = NULL;

    if (fsm->encoding_path == PATH_PROTO) {
        out = encode_payload(src, &fsm->config);
    } else {
        LegacyEvent_CC* ev = build_legacy_event(src, "DATA_EVENT");
        out = serialize_wsdl(ev);
        dispatch_event("MSG_SENT", out);
    }
    fsm->state = P_WAITING_ACK;
}

// WAITING_ACK: block until ACK or timeout
void handle_waiting_ack(ProducerFSM* fsm) {
    if (fsm->ack_received) {
        fsm->ack_received = 0;
        fsm->state = P_IDLE;
    } else {
        timeout_event(fsm);
    }
}

// ERROR: recover or escalate
void handle_error(ProducerFSM* fsm) {
    dispatch_event("ERROR", NULL);
    if (fsm->retry_count < fsm->config.retry_limit) {
        fsm->retry_count++;
        fsm->state = P_IDLE;
    } else {
        fsm->state = P_FATAL;
    }
}

void trigger_event(ProducerFSM* fsm)    { fsm->state = P_ENCODING; }
void ack_received_event(ProducerFSM* fsm) { fsm->ack_received = 1; }
void timeout_event(ProducerFSM* fsm)    { fsm->state = P_ERROR; }
void error_event(ProducerFSM* fsm)      { fsm->state = P_ERROR; }
