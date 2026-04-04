package com.stresstest.client;

import com.stresstest.messages.Envelope;

/**
 * BaseProcessor — base class for testing super.method() resolution.
 *
 * Defines process(Envelope) and reset() methods that will be called
 * via super. from DerivedProcessor.
 */
public class BaseProcessor {

    protected int processedCount;

    public BaseProcessor() {
        this.processedCount = 0;
    }

    public void process(Envelope env) {
        if (env != null) {
            processedCount++;
        }
    }

    public void reset() {
        processedCount = 0;
    }

    public int getProcessedCount() {
        return processedCount;
    }
}
