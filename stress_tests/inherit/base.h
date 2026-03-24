#pragma once

// Base class with a concrete method that derived classes can call bare (no qualifier).
// Inheritance stress test: verifies that DerivedClass::method() calling process()
// bare resolves to Base.process, not unresolved::process.
class Base {
public:
    void process(int value);
    void reset();
};
