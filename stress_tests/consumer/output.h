#pragma once
#include "processor.h"

// RawBytes (matches other service definitions)
// (would be shared header in real build)

// EventBus forward declaration
struct EventBus {
    void subscribe(const char* event, void (*cb)(const char*, void*));
    void publish(const char* event, void* data);
};

// Consumer-local dispatch_event wrapper.
// IMPORTANT: one of THREE local dispatch_event functions (producer, broker, consumer).
// All call EventBus::publish. 3 symbol nodes → 1 EventBus type node.
// WRITE_COMPLETE fired here is the ACK that releases Producer:WAITING_ACK.
void dispatch_event(const char* event, void* data);

// Write processed payload to sink
// consumes: ProcessedPayload* (role:data)
// produces: int success flag (via return_value)
int write_output(const ProcessedPayload* payload);

// Consumer error and ACK callback handlers
void consumer_on_error(const char* event, void* data);
void consumer_subscribe_all(EventBus* bus);
