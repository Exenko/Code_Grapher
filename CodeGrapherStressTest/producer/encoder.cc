#include "encoder.h"
#include "callbacks.h"
#include "types.h"
#include <stdlib.h>
#include <string.h>

// encode_payload: top of the proto-path call chain (depth 1 of 5)
// consumes: PayloadHandlePP (ptr_depth=3 dereference chain)
// produces: RawBytes* (serialized output)
RawBytes* encode_payload(PayloadHandlePP src, const ProducerConfig* cfg) {
    int path = select_serializer(cfg);
    Payload flat = **src;           // dereference PayloadHandlePP → PayloadHandle → Payload
    Envelope env = { /* build from flat */ };
    RawBytes* out = serialize_proto(&env);
    int ok = transmit_message(out, "broker");
    if (ok) {
        dispatch_event("MSG_SENT", out);
    }
    return out;
}

// select_serializer: depth 2 of 5
// consumes: ProducerConfig* (role:control — shapes behavior, data doesn't flow to output)
// returns 1 = proto, 0 = legacy
int select_serializer(const ProducerConfig* cfg) {
    return cfg->use_proto;
}

// serialize_proto: depth 3 of 5
// consumes: Envelope* (role:data)
// produces: RawBytes* (via return_value)
RawBytes* serialize_proto(const Envelope* env) {
    RawBytes* out = (RawBytes*)malloc(sizeof(RawBytes));
    /* protobuf serialize env into out->data */
    return out;
}

// transmit_message: depth 4 of 5
// consumes: RawBytes* (data to send), destination string
// produces: int (success flag, via return_value)
int transmit_message(RawBytes* data, const char* destination) {
    /* TCP send via abstraction layer */
    return 1;
}
