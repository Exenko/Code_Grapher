#include "state_machine.h"
#include "output.h"

// Consumer entry point.
// CodeGrapher should detect this as a main() entry point and build
// a sub-graph rooted here following the 6-hop internal call chain
// (hits depth cap exactly at transform()).
int main(int argc, char* argv[]) {
    EventBus bus;
    ConsumerFSM fsm;

    consumer_fsm_init(&fsm, &bus);
    consumer_fsm_run(&fsm);

    return 0;
}
