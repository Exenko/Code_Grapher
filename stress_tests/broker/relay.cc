#include "relay.h"
#include "router.h"
#include <stdlib.h>
#include <string.h>

// Global broker EventBus instance
static EventBus g_broker_bus;

// Global routing table (loaded from config at startup)
static RoutingTable* g_routing_table = NULL;

// Broker-local dispatch_event.
// Calls EventBus::publish — convergence point shared with producer and consumer wrappers.
// relay:true — broker did not originate this event, it is forwarding upstream data.
void dispatch_event(const char* event, RawBytes* data) {
    g_broker_bus.publish(event, data);
}

// on_msg_received: top of the broker call chain (depth 1 of 4)
// consumes: RawBytes* msg (role:data — the actual message, relay:true)
// consumes: Session* session (role:control — tracks connection state)
// produces: nothing directly — side effect is forward_message call
void on_msg_received(RawBytes* msg, Session* session) {
    // depth 2: inspect_header
    RoutingKey* key = inspect_header(msg->data, (int)msg->len);
    // depth 3: lookup_route (consumes routing table, role:control)
    const char* dest = lookup_route(key, g_routing_table);
    // depth 4: forward_message
    int ok = forward_message(msg, dest);
    if (ok) {
        dispatch_event("MSG_FORWARDED", msg); // relay:true — msg originated upstream
    } else {
        dispatch_event("ERROR", NULL);
    }
    free(key);
}

// forward_message: sends relay message to consumer
// consumes: RawBytes* msg (role:data, relay:true — originated upstream)
// consumes: destination string (role:control)
// produces: int success flag (via return_value)
int forward_message(RawBytes* msg, const char* destination) {
    /* TCP send to destination */
    return 1;
}

Session* session_create(const char* session_id) {
    Session* s = (Session*)malloc(sizeof(Session));
    s->session_id = session_id;
    s->header     = NULL;
    s->ttl        = 30;
    s->active     = 1;
    return s;
}

void session_destroy(Session* session) {
    free(session);
}

void broker_subscribe_all(EventBus* bus) {
    bus->subscribe("ERROR", broker_on_error);
}

void broker_on_error(const char* event, RawBytes* data) {
    /* log and enter ERROR_RECOVERY state */
    dispatch_event("ERROR", data); // relay error notification to peers
}
