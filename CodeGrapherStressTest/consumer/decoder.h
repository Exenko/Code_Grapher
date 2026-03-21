#pragma once
#include <stdint.h>
#include <stddef.h>

// Wire format indicator
typedef enum WireFormat {
    FORMAT_PROTO,
    FORMAT_LEGACY_WSDL,
    FORMAT_UNKNOWN
} WireFormat;

// Decoded message — canonical internal form after either decode path
struct DecodedMessage {
    WireFormat  format;
    const char* event_type;
    uint8_t*    payload_data;
    size_t      payload_len;
    uint64_t    sequence_num;
    int         version;
};

// Proto Envelope forward declaration (defined in proto/messages.proto)
struct Envelope;
// LegacyEvent_CC forward declaration (defined in producer/legacy_encoder.h)
struct LegacyEvent_CC;

// RawBytes (matches producer definition)
struct RawBytes {
    uint8_t* data;
    size_t   len;
};

// depth 2 of 6: detect wire format from magic bytes / schema indicator
// consumes: RawBytes* (role:data)
// produces: WireFormat (via return_value)
WireFormat detect_format(const RawBytes* raw);

// depth 3 of 6: dispatch to correct decoder
// consumes: RawBytes* (role:data), WireFormat (role:control — determines path)
// produces: DecodedMessage* (via return_value)
DecodedMessage* decode_message(const RawBytes* raw, WireFormat fmt);

// Proto decode path
// consumes: RawBytes* (role:data)
// produces: DecodedMessage* (via return_value)
DecodedMessage* decode_proto(const RawBytes* raw);

// WSDL/legacy decode path
// consumes: RawBytes* (role:data)
// produces: DecodedMessage* (via return_value)
// maps_to: LegacyEvent_CC (C++ side of wsdl→proto→cc bridge)
DecodedMessage* decode_wsdl(const RawBytes* raw);
