#include "state_machine.h"
#include <stdlib.h>

void consumer_fsm_init(ConsumerFSM* fsm, EventBus* bus) {
    fsm->state           = C_WAITING;
    fsm->bus             = bus;
    fsm->current_msg     = NULL;
    fsm->current_payload = NULL;
    fsm->retry_count     = 0;
    consumer_subscribe_all(bus);
}

void consumer_fsm_run(ConsumerFSM* fsm) {
    while (1) {
        switch (fsm->state) {
            case C_WAITING:    consumer_handle_waiting(fsm);    break;
            case C_DECODING:   /* triggered via on_msg_received */ break;
            case C_PROCESSING: consumer_handle_processing(fsm); break;
            case C_WRITING:    consumer_handle_writing(fsm);    break;
            case C_ERROR:      consumer_handle_error(fsm);      break;
        }
    }
}

// WAITING: idle on socket, unblocked by MSG_FORWARDED from Broker
void consumer_handle_waiting(ConsumerFSM* fsm) {
    /* block until on_msg_received fires */
}

// on_msg_received: depth 1 of 6 — top of consumer call chain
// Called when Broker fires dispatch_event("MSG_FORWARDED")
// consumes: RawBytes* msg (role:data), ConsumerFSM* (role:control)
void on_msg_received(RawBytes* msg, ConsumerFSM* fsm) {
    fsm->state = C_DECODING;
    consumer_handle_decoding(fsm, msg);
}

// DECODING → PROCESSING: depth 2-3 of 6 happen inside here
void consumer_handle_decoding(ConsumerFSM* fsm, RawBytes* raw) {
    WireFormat fmt = detect_format(raw);          // depth 2 of 6
    DecodedMessage* msg = decode_message(raw, fmt); // depth 3 of 6
    if (msg == NULL) {
        dispatch_event("ERROR", NULL);
        fsm->state = C_ERROR;
        return;
    }
    fsm->current_msg = msg;
    fsm->state = C_PROCESSING;
    consumer_handle_processing(fsm);
}

// PROCESSING: depth 4-6 of 6 happen inside here
void consumer_handle_processing(ConsumerFSM* fsm) {
    // process_payload runs sub-FSM: VALIDATING → TRANSFORMING → ENRICHING
    ProcessedPayload* result = process_payload(fsm->current_msg); // depth 4-6 of 6
    if (result == NULL) {
        dispatch_event("ERROR", NULL);
        fsm->state = C_ERROR;
        return;
    }
    fsm->current_payload = result;
    fsm->state = C_WRITING;
    consumer_handle_writing(fsm);
}

// WRITING → WAITING: fires WRITE_COMPLETE (the ACK to Producer)
void consumer_handle_writing(ConsumerFSM* fsm) {
    int ok = write_output(fsm->current_payload); // fires dispatch_event("WRITE_COMPLETE") internally
    if (ok) {
        fsm->current_msg     = NULL;
        fsm->current_payload = NULL;
        fsm->retry_count     = 0;
        fsm->state = C_WAITING;
    } else {
        dispatch_event("ERROR", NULL);
        fsm->state = C_ERROR;
    }
}

// ERROR → WAITING on recover
void consumer_handle_error(ConsumerFSM* fsm) {
    fsm->retry_count++;
    fsm->state = C_WAITING;
}
