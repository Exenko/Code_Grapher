#pragma once
#include "decoder.h"
#include "processor.h"
#include "output.h"

// Consumer FSM states
typedef enum ConsumerState {
    C_WAITING,
    C_DECODING,
    C_PROCESSING,
    C_WRITING,
    C_ERROR
} ConsumerState;

struct ConsumerFSM {
    ConsumerState     state;
    EventBus*         bus;
    DecodedMessage*   current_msg;
    ProcessedPayload* current_payload;
    int               retry_count;
};

void consumer_fsm_init(ConsumerFSM* fsm, EventBus* bus);
void consumer_fsm_run(ConsumerFSM* fsm);

// State handlers
void consumer_handle_waiting(ConsumerFSM* fsm);
void consumer_handle_decoding(ConsumerFSM* fsm, RawBytes* raw);
void consumer_handle_processing(ConsumerFSM* fsm);
void consumer_handle_writing(ConsumerFSM* fsm);
void consumer_handle_error(ConsumerFSM* fsm);

// Entry point for incoming message (depth 1 of 6)
// Called when MSG_FORWARDED event fires from Broker
void on_msg_received(RawBytes* msg, ConsumerFSM* fsm);
