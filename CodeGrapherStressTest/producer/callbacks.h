#pragma once
#include "types.h"

// Producer-local dispatch_event wrapper.
// IMPORTANT: this is one of THREE local dispatch_event functions
// (one per service). All call EventBus::publish. This is intentionally
// hard to trace — 3 symbol nodes converge on 1 EventBus type node.
void dispatch_event(const char* event, RawBytes* data);

// Called by EventBus when any subscribed event fires.
void on_state_change(const char* event, RawBytes* data);

// Registration helpers
void subscribe_all(EventBus* bus);
void register_callbacks(EventBus* bus);
