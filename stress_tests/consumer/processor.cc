#include "processor.h"
#include <stdlib.h>
#include <string.h>

// process_payload: depth 4 of 6
// Runs the processing sub-FSM: VALIDATING → TRANSFORMING → ENRICHING
// consumes: DecodedMessage* (role:data)
// produces: ProcessedPayload* (via return_value)
ProcessedPayload* process_payload(DecodedMessage* msg) {
    ProcessingState state = PROC_VALIDATING;
    ProcessedPayload* result = NULL;

    // Sub-FSM: VALIDATING
    int ok = validate(msg);
    if (!ok) {
        state = PROC_ERROR;
        return NULL; // PROC_ERROR → abort
    }

    // Sub-FSM: TRANSFORMING
    state = PROC_TRANSFORMING;
    result = transform(msg); // depth 5 of 6

    // Sub-FSM: ENRICHING
    state = PROC_ENRICHING;
    enrich(result); // param_mutation: enriches result in place

    return result;
}

// validate: depth 5 of 6
// consumes: DecodedMessage* (role:data)
// produces: int (via return_value — 1=valid, 0=invalid)
int validate(const DecodedMessage* msg) {
    if (msg == NULL)                return 0;
    if (msg->payload_data == NULL)  return 0;
    if (msg->payload_len == 0)      return 0;
    if (msg->format == FORMAT_UNKNOWN) return 0;
    return 1;
}

// transform: depth 6 of 6 — DEPTH CAP FIRES AFTER THIS
// Normalizes DecodedMessage into canonical ProcessedPayload form.
// consumes: DecodedMessage* (role:data)
// produces: ProcessedPayload* (via return_value)
ProcessedPayload* transform(DecodedMessage* msg) {
    ProcessedPayload* p = (ProcessedPayload*)malloc(sizeof(ProcessedPayload));
    p->source          = msg;
    p->canonical_type  = msg->event_type;
    p->normalized_data = msg->payload_data;
    p->normalized_len  = msg->payload_len;
    p->metadata        = NULL;
    p->valid           = 1;
    return p;
}

// enrich: attaches metadata to processed payload (in-place mutation)
// consumes: ProcessedPayload* (param_mutation — mutates caller's struct)
// produces: ProcessedPayload* via param_mutation (relay:false — metadata originates here)
void enrich(ProcessedPayload* payload) {
    payload->metadata = "enriched:v1";
    /* additional metadata lookups, reference data joins, etc. */
}
