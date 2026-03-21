#include "state_machine.h"
#include <stdlib.h>

void broker_fsm_init(BrokerFSM* fsm, EventBus* bus, const char* config_path) {
    fsm->state           = B_LISTENING;
    fsm->bus             = bus;
    fsm->routing_table   = load_routing_table(config_path);
    fsm->current_session = NULL;
    fsm->retry_count     = 0;
    fsm->max_retries     = 3;
    broker_subscribe_all(bus);
}

void broker_fsm_run(BrokerFSM* fsm) {
    RawBytes* incoming = NULL; /* would come from socket */
    while (1) {
        switch (fsm->state) {
            case B_LISTENING:
                broker_handle_listening(fsm, incoming);
                break;
            case B_ROUTING:
                broker_handle_routing(fsm, incoming);
                break;
            case B_FORWARDING: {
                RoutingKey* key = inspect_header(incoming->data, (int)incoming->len);
                const char* dest = lookup_route(key, fsm->routing_table);
                broker_handle_forwarding(fsm, incoming, dest);
                free(key);
                break;
            }
            case B_ERROR_RECOVERY: {
                RoutingKey* key = inspect_header(incoming->data, (int)incoming->len);
                const char* dest = lookup_route(key, fsm->routing_table);
                broker_handle_error_recovery(fsm, incoming, dest);
                free(key);
                break;
            }
        }
    }
}

// LISTENING → ROUTING on msg_received
void broker_handle_listening(BrokerFSM* fsm, RawBytes* incoming) {
    if (incoming != NULL) {
        fsm->current_session = session_create("session-001");
        on_msg_received(incoming, fsm->current_session);
        fsm->state = B_ROUTING;
    }
}

// ROUTING → FORWARDING on route_resolved
void broker_handle_routing(BrokerFSM* fsm, RawBytes* msg) {
    /* routing logic delegated to on_msg_received / lookup_route */
    fsm->state = B_FORWARDING;
}

// FORWARDING → LISTENING on success, → ERROR_RECOVERY on failure
void broker_handle_forwarding(BrokerFSM* fsm, RawBytes* msg, const char* dest) {
    int ok = forward_message(msg, dest);
    if (ok) {
        dispatch_event("MSG_FORWARDED", msg);
        session_destroy(fsm->current_session);
        fsm->current_session = NULL;
        fsm->retry_count = 0;
        fsm->state = B_LISTENING;
    } else {
        fsm->state = B_ERROR_RECOVERY;
    }
}

// ERROR_RECOVERY → LISTENING on retry_success_or_drop
void broker_handle_error_recovery(BrokerFSM* fsm, RawBytes* msg, const char* dest) {
    dispatch_event("ERROR", NULL);
    if (fsm->retry_count < fsm->max_retries) {
        fsm->retry_count++;
        int ok = forward_message(msg, dest);
        if (ok) {
            dispatch_event("MSG_FORWARDED", msg);
            fsm->state = B_LISTENING;
        }
    } else {
        /* drop message */
        fsm->retry_count = 0;
        fsm->state = B_LISTENING;
    }
}
