#include "legacy_encoder.h"
#include "callbacks.h"
#include "types.h"
#include <stdlib.h>
#include <string.h>

// build_legacy_event: constructs LegacyEvent_CC from raw payload
// consumes: PayloadHandlePP (ptr_depth=3), event_type string
// produces: LegacyEvent_CC* (via return_value)
LegacyEvent_CC* build_legacy_event(PayloadHandlePP src, const char* event_type) {
    LegacyEvent_CC* ev = (LegacyEvent_CC*)malloc(sizeof(LegacyEvent_CC));
    ev->event_type = event_type;
    ev->payload    = *src;      // dereference PayloadHandlePP → PayloadHandle
    ev->version    = 1;
    return ev;
}

// serialize_wsdl: WSDL encoding path
// consumes: LegacyEvent_CC* (role:data)
// produces: RawBytes* (via return_value) — WSDL XML serialization
RawBytes* serialize_wsdl(const LegacyEvent_CC* ev) {
    RawBytes* out = (RawBytes*)malloc(sizeof(RawBytes));
    /* WSDL/XML serialize ev into out->data */
    /* format: <LegacyEvent><event_type>...</event_type><payload>...</payload></LegacyEvent> */
    return out;
}
