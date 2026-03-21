#pragma once
#include "types.h"

// Forward declare proto-generated type
struct Envelope;
struct Header;

// Proto encoding path (config flag = proto)
// Internal call chain depth 5:
// encode_payload → select_serializer → serialize_proto → transmit_message → dispatch_event
RawBytes* encode_payload(PayloadHandlePP src, const ProducerConfig* cfg);
int       select_serializer(const ProducerConfig* cfg);
RawBytes* serialize_proto(const Envelope* env);
int       transmit_message(RawBytes* data, const char* destination);
