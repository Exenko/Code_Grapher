package com.stresstest.client;

import com.stresstest.messages.Envelope;

/**
 * DerivedProcessor — extends BaseProcessor and tests super.method() resolution.
 *
 * Overrides process() and calls super.process(env) and super.reset()
 * to exercise the super.method() call resolution path in the Java parser.
 */
public class DerivedProcessor extends BaseProcessor {

    private int filterCount;

    public DerivedProcessor() {
        super();
        this.filterCount = 0;
    }

    @Override
    public void process(Envelope env) {
        // Call super.process(env) — should resolve to BaseProcessor.process()
        super.process(env);
        filterCount++;
    }

    public void clearAll() {
        // Call super.reset() — should resolve to BaseProcessor.reset()
        super.reset();
        filterCount = 0;
    }

    public int getFilterCount() {
        return filterCount;
    }
}
