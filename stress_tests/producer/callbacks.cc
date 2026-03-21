#include "callbacks.h"
#include "types.h"
#include <string.h>

// Global EventBus instance (producer-side)
static EventBus g_bus;

// Producer-local dispatch_event.
// Calls EventBus::publish — this is the convergence point.
void dispatch_event(const char* event, RawBytes* data) {
    g_bus.publish(event, data);
}

void on_state_change(const char* event, RawBytes* data) {
    if (strcmp(event, "WRITE_COMPLETE") == 0) {
        // ACK received — producer can transition WAITING_ACK → IDLE
        /* signal state machine */
    } else if (strcmp(event, "ERROR") == 0) {
        /* notify producer error handler */
    }
}

void subscribe_all(EventBus* bus) {
    register_callbacks(bus);
}

void register_callbacks(EventBus* bus) {
    bus->subscribe("WRITE_COMPLETE", on_state_change);
    bus->subscribe("ERROR", on_state_change);
}
