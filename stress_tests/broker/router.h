#pragma once
#include <stdint.h>

// RoutingKey — defined in Broker, but referenced by proto Header.
// This creates a cross-file contains edge: Header contains RoutingKey.
struct RoutingKey {
    const char* destination;
    int32_t     priority;
    uint32_t    flags;
};

// RouteEntry — one entry in the routing table (loaded from XML config)
struct RouteEntry {
    RoutingKey  key;
    const char* target_address;
    int         weight;
};

// RoutingTable — populated from broker_config.xml (role:control)
struct RoutingTable {
    RouteEntry* entries;
    int         count;
};

// Inspect the message header and extract routing key
// consumes: raw header bytes (role:data)
// produces: RoutingKey* (via return_value)
RoutingKey* inspect_header(const void* header_bytes, int len);

// Look up destination from routing table
// consumes: RoutingKey* (role:data), RoutingTable* (role:control)
// produces: const char* destination (via return_value)
// relay:true — data originates upstream, broker just routes it
const char* lookup_route(const RoutingKey* key, const RoutingTable* table);

// Load routing table from XML config file (role:control input)
// consumes: config_path string
// produces: RoutingTable* (via return_value)
RoutingTable* load_routing_table(const char* config_path);
