#pragma once
#include "types.h"

// LegacyEvent_CC — C++ representation of LegacyEvent.
// maps_to: LegacyEvent_Proto (proto/legacy.proto)
// maps_to: LegacyEvent_WSDL (wsdl/legacy_types.xml)
struct LegacyEvent_CC {
    const char*   event_type;
    PayloadHandle payload;   // ptr_depth=2: PayloadHandle = Payload* = MessageBody** = RawBytes**
    int           version;
};

// WSDL encoding path (config flag = legacy)
RawBytes* serialize_wsdl(const LegacyEvent_CC* ev);
LegacyEvent_CC* build_legacy_event(PayloadHandlePP src, const char* event_type);
