#include "decoder.h"
#include <stdlib.h>
#include <string.h>

// Magic byte constants for format detection
#define PROTO_MAGIC   0xPB
#define WSDL_MAGIC    0x3C  // '<' (XML opening tag)

// detect_format: depth 2 of 6
// Inspects first byte to determine wire format.
// consumes: RawBytes* (role:data)
// produces: WireFormat (via return_value)
WireFormat detect_format(const RawBytes* raw) {
    if (raw == NULL || raw->len == 0) return FORMAT_UNKNOWN;
    if (raw->data[0] == 0x0A) return FORMAT_PROTO;       // protobuf field tag
    if (raw->data[0] == 0x3C) return FORMAT_LEGACY_WSDL; // XML '<'
    return FORMAT_UNKNOWN;
}

// decode_message: depth 3 of 6
// Dispatches to proto or WSDL decoder based on format (role:control).
// consumes: RawBytes* (role:data), WireFormat (role:control)
// produces: DecodedMessage* (via return_value)
DecodedMessage* decode_message(const RawBytes* raw, WireFormat fmt) {
    switch (fmt) {
        case FORMAT_PROTO:       return decode_proto(raw);
        case FORMAT_LEGACY_WSDL: return decode_wsdl(raw);
        default:                 return NULL;
    }
}

// decode_proto: proto decode path
// consumes: RawBytes* containing serialized Envelope
// produces: DecodedMessage* (via return_value)
DecodedMessage* decode_proto(const RawBytes* raw) {
    DecodedMessage* msg = (DecodedMessage*)malloc(sizeof(DecodedMessage));
    msg->format       = FORMAT_PROTO;
    msg->event_type   = "DATA_EVENT";
    msg->payload_data = raw->data;
    msg->payload_len  = raw->len;
    msg->sequence_num = 0;
    msg->version      = 2;
    /* deserialize raw->data as protobuf Envelope */
    return msg;
}

// decode_wsdl: WSDL/legacy decode path
// consumes: RawBytes* containing serialized LegacyEvent XML
// produces: DecodedMessage* (via return_value)
// This path is the C++ end of the maps_to chain:
//   LegacyEvent_WSDL (xml) → LegacyEvent_Proto (proto) → LegacyEvent_CC (C++) → DecodedMessage
DecodedMessage* decode_wsdl(const RawBytes* raw) {
    DecodedMessage* msg = (DecodedMessage*)malloc(sizeof(DecodedMessage));
    msg->format       = FORMAT_LEGACY_WSDL;
    msg->event_type   = "LEGACY_DATA_EVENT";
    msg->payload_data = raw->data;
    msg->payload_len  = raw->len;
    msg->sequence_num = 0;
    msg->version      = 1;
    /* deserialize raw->data as WSDL XML LegacyEvent */
    return msg;
}
