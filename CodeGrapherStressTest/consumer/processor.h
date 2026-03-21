#pragma once
#include "decoder.h"

// Processing sub-FSM states (nested inside Consumer PROCESSING state)
typedef enum ProcessingState {
    PROC_VALIDATING,
    PROC_TRANSFORMING,
    PROC_ENRICHING,
    PROC_ERROR
} ProcessingState;

// ProcessedPayload — canonical output after full processing pipeline
struct ProcessedPayload {
    DecodedMessage* source;
    const char*     canonical_type;
    uint8_t*        normalized_data;
    size_t          normalized_len;
    const char*     metadata;
    int             valid;
};

// depth 4 of 6: top of processing sub-pipeline
// consumes: DecodedMessage* (role:data)
// produces: ProcessedPayload* (via return_value)
ProcessedPayload* process_payload(DecodedMessage* msg);

// depth 5 of 6: validate decoded payload against schema
// consumes: DecodedMessage* (role:data)
// produces: int valid flag (via return_value)
int validate(const DecodedMessage* msg);

// depth 6 of 6: normalize to canonical internal form
// consumes: DecodedMessage* (role:data)
// produces: ProcessedPayload* (via return_value)
// NOTE: this is depth 6 — the call chain cap fires after this
ProcessedPayload* transform(DecodedMessage* msg);

// Called after transform — attaches metadata
// consumes: ProcessedPayload* (param_mutation — enriches in place)
// produces: ProcessedPayload* (via param_mutation, relay:false — enriched here)
void enrich(ProcessedPayload* payload);
