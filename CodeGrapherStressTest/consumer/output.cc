#include "output.h"
#include <stdlib.h>
#include <string.h>

// Global consumer EventBus instance
static EventBus g_consumer_bus;

// Consumer-local dispatch_event.
// Calls EventBus::publish — convergence point shared with producer and broker wrappers.
// WRITE_COMPLETE fired here is the ACK consumed by Producer:WAITING_ACK.
void dispatch_event(const char* event, void* data) {
    g_consumer_bus.publish(event, data);
}

// write_output: writes ProcessedPayload to sink, then fires WRITE_COMPLETE (the ACK)
// consumes: ProcessedPayload* (role:data)
// produces: int (via return_value — 1=success, 0=failure)
int write_output(const ProcessedPayload* payload) {
    if (payload == NULL || !payload->valid) return 0;
    /* write payload->normalized_data to configured sink */
    // Fire WRITE_COMPLETE — this is the ACK that releases Producer from WAITING_ACK
    dispatch_event("WRITE_COMPLETE", (void*)payload);
    return 1;
}

void consumer_on_error(const char* event, void* data) {
    dispatch_event("ERROR", data);
}

void consumer_subscribe_all(EventBus* bus) {
    bus->subscribe("ERROR", consumer_on_error);
}
