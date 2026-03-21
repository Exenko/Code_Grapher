#include "state_machine.h"
#include "callbacks.h"
#include "types.h"

// Producer entry point.
// CodeGrapher should detect this as a main() entry point and build
// a sub-graph rooted here, following the 5-hop internal call chain.
int main(int argc, char* argv[]) {
    ProducerConfig cfg;
    cfg.use_proto     = 1;   // read from config/producer_config.xml at runtime
    cfg.retry_limit   = 3;
    cfg.ack_timeout_ms = 5000;

    EventBus bus;
    ProducerFSM fsm;

    producer_fsm_init(&fsm, &bus, &cfg);
    producer_fsm_run(&fsm);

    return 0;
}
