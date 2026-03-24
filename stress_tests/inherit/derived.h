#pragma once
#include "base.h"

// Derived inherits Base. doWork() and initialize() are defined in derived.cc
// and make bare calls to process() and reset() — inherited from Base.
class Derived : public Base {
public:
    void doWork(int value);
    void initialize();
};
