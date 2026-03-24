#include "derived.h"

// Derived::doWork makes a bare call to process() — inherited from Base.
// Expected: calls edge Derived.doWork -> Base.process (resolved, not unresolved).
void Derived::doWork(int value) {
    process(value);
}

// Derived::initialize makes a bare call to reset() — inherited from Base.
// Expected: calls edge Derived.initialize -> Base.reset (resolved, not unresolved).
void Derived::initialize() {
    reset();
}
