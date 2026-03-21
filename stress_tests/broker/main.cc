#include "state_machine.h"
#include "relay.h"

// Broker entry point.
// CodeGrapher should detect this as a main() entry point and build
// a sub-graph rooted here, following the 4-hop internal call chain.
int main(int argc, char* argv[]) {
    const char* config_path = "config/broker_config.xml";

    EventBus bus;
    BrokerFSM fsm;

    broker_fsm_init(&fsm, &bus, config_path);
    broker_fsm_run(&fsm);

    return 0;
}
