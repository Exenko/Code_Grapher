#include "router.h"
#include <stdlib.h>
#include <string.h>

// load_routing_table: reads broker_config.xml
// This data is role:control — it shapes routing behavior but its
// content does not flow into the forwarded message payload.
RoutingTable* load_routing_table(const char* config_path) {
    RoutingTable* table = (RoutingTable*)malloc(sizeof(RoutingTable));
    /* parse XML config_path into table->entries */
    table->entries = NULL;
    table->count   = 0;
    return table;
}

// inspect_header: extracts routing key from raw bytes
// produces RoutingKey* relay:true — key came from upstream producer
RoutingKey* inspect_header(const void* header_bytes, int len) {
    RoutingKey* key = (RoutingKey*)malloc(sizeof(RoutingKey));
    /* parse header_bytes to populate key fields */
    key->destination = "consumer-default";
    key->priority    = 0;
    key->flags       = 0;
    return key;
}

// lookup_route: consults routing table (role:control) to find destination
// relay:true — broker is forwarding, not originating the destination decision
const char* lookup_route(const RoutingKey* key, const RoutingTable* table) {
    for (int i = 0; i < table->count; i++) {
        if (strcmp(table->entries[i].key.destination, key->destination) == 0) {
            return table->entries[i].target_address;
        }
    }
    return key->destination; // fallback: use key destination directly
}
