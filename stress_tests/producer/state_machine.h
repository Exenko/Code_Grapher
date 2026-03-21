#pragma once
#include "types.h"

// Producer FSM states
typedef enum ProducerState {
    P_IDLE,
    P_ENCODING,
    P_TRANSMITTING,
    P_WAITING_ACK,
    P_ERROR,
    P_FATAL
} ProducerState;

// Encoding sub-path selection
typedef enum EncodingPath {
    PATH_PROTO,
    PATH_LEGACY_WSDL
} EncodingPath;

struct ProducerFSM {
    ProducerState   state;
    EncodingPath    encoding_path;
    ProducerConfig  config;
    EventBus*       bus;
    int             ack_received;
    int             retry_count;
};

// FSM lifecycle
void producer_fsm_init(ProducerFSM* fsm, EventBus* bus, const ProducerConfig* cfg);
void producer_fsm_run(ProducerFSM* fsm);

// State transition handlers
void handle_idle(ProducerFSM* fsm);
void handle_encoding(ProducerFSM* fsm);
void handle_transmitting(ProducerFSM* fsm);
void handle_waiting_ack(ProducerFSM* fsm);
void handle_error(ProducerFSM* fsm);

// External event injection (called by callback system)
void trigger_event(ProducerFSM* fsm);
void ack_received_event(ProducerFSM* fsm);
void timeout_event(ProducerFSM* fsm);
void error_event(ProducerFSM* fsm);
