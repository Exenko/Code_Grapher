#pragma once
#include "relay.h"
#include "router.h"

// Broker FSM states
typedef enum BrokerState {
    B_LISTENING,
    B_ROUTING,
    B_FORWARDING,
    B_ERROR_RECOVERY
} BrokerState;

struct BrokerFSM {
    BrokerState    state;
    Session*       current_session;
    RoutingTable*  routing_table;
    EventBus*      bus;
    int            retry_count;
    int            max_retries;
};

void broker_fsm_init(BrokerFSM* fsm, EventBus* bus, const char* config_path);
void broker_fsm_run(BrokerFSM* fsm);

void broker_handle_listening(BrokerFSM* fsm, RawBytes* incoming);
void broker_handle_routing(BrokerFSM* fsm, RawBytes* msg);
void broker_handle_forwarding(BrokerFSM* fsm, RawBytes* msg, const char* dest);
void broker_handle_error_recovery(BrokerFSM* fsm, RawBytes* msg, const char* dest);
