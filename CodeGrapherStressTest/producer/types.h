#pragma once
#include <stdint.h>
#include <stddef.h>

// RawBytes — the base concrete struct
struct RawBytes {
    uint8_t* data;
    size_t   len;
};

// Typedef chain (ptr_depth 0 → 3):
// MessageBody is a direct alias (ptr_depth=0)
typedef RawBytes MessageBody;
// Payload is a pointer alias (ptr_depth=1)
typedef MessageBody* Payload;
// PayloadHandle is pointer-to-pointer (ptr_depth=2)
typedef Payload* PayloadHandle;
// PayloadHandlePP is triple pointer (ptr_depth=3)
typedef PayloadHandle* PayloadHandlePP;

// Callback function pointer typedef
typedef void (*Callback)(const char* event, RawBytes* data);

// EventBus — shared cross-cutting type
// All three services (producer, broker, consumer) have their own
// local dispatch_event() wrapper that calls into EventBus::publish.
struct EventBus {
    void subscribe(const char* event, Callback cb);
    void publish(const char* event, RawBytes* data);
};

// ProducerConfig — read from XML, used as role:control
struct ProducerConfig {
    int  use_proto;   // 1 = proto path, 0 = legacy WSDL path
    int  retry_limit;
    int  ack_timeout_ms;
};
