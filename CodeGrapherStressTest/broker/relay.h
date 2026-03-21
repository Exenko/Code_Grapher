#pragma once
#include "router.h"
#include <stdint.h>

// Need RawBytes from producer types — in a real build this would be a shared header
struct RawBytes {
    uint8_t* data;
    size_t   len;
};

// Session — broker-side session tracker.
// contains Header (Header defined in proto/messages.proto — cross-file contains edge).
// For static analysis purposes, Header is forward-declared here.
struct Header;

struct Session {
    const char* session_id;
    Header*     header;     // contains edge: Session → Header (ptr_depth=1)
    uint32_t    ttl;
    int         active;
};

// EventBus forward declaration (defined in producer/types.h in full build)
struct EventBus {
    void subscribe(const char* event, void (*cb)(const char*, RawBytes*));
    void publish(const char* event, RawBytes* data);
};

// Broker-local dispatch_event wrapper.
// IMPORTANT: one of THREE local dispatch_event functions (producer, broker, consumer).
// All call EventBus::publish. 3 symbol nodes → 1 EventBus type node.
void dispatch_event(const char* event, RawBytes* data);

// Main broker receive/forward chain (depth 4):
// on_msg_received → inspect_header → lookup_route → forward_message → dispatch_event
void on_msg_received(RawBytes* msg, Session* session);
int  forward_message(RawBytes* msg, const char* destination);

// Session management
Session* session_create(const char* session_id);
void     session_destroy(Session* session);

// Subscription setup
void broker_subscribe_all(EventBus* bus);
void broker_on_error(const char* event, RawBytes* data);
