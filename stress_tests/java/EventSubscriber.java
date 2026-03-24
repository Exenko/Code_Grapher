package com.stresstest.client;

import com.stresstest.events.EventEnvelope;
import com.stresstest.events.EventType;
import com.stresstest.events.AckEvent;
import com.stresstest.events.ErrorEvent;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * EventSubscriber — consumes events published by the C++ EventBus.
 *
 * Mirrors the broker_subscribe_all / consumer_subscribe_all pattern in C++.
 * Receives EventEnvelope, AckEvent, ErrorEvent — all proto-defined types,
 * creating cross-language type bridge edges from Java to events.proto.
 */
public class EventSubscriber {

    public interface EventHandler {
        void handle(EventEnvelope event);
    }

    private Map<EventType, List<EventHandler>> handlers;
    private List<AckEvent> ackLog;
    private List<ErrorEvent> errorLog;
    private int processedCount;

    public EventSubscriber() {
        this.handlers = new HashMap<>();
        this.ackLog = new ArrayList<>();
        this.errorLog = new ArrayList<>();
        this.processedCount = 0;
    }

    public void subscribe(EventType type, EventHandler handler) {
        handlers.computeIfAbsent(type, k -> new ArrayList<>()).add(handler);
    }

    public void onEvent(EventEnvelope envelope) {
        processedCount++;
        dispatch(envelope);
    }

    private void dispatch(EventEnvelope envelope) {
        EventType type = envelope.getEventType();
        List<EventHandler> typeHandlers = handlers.get(type);
        if (typeHandlers != null) {
            for (EventHandler h : typeHandlers) {
                h.handle(envelope);
            }
        }
        routeByType(envelope);
    }

    private void routeByType(EventEnvelope envelope) {
        switch (envelope.getEventType()) {
            case MSG_SENT:
                handleMsgSent(envelope);
                break;
            case MSG_FORWARDED:
                handleMsgForwarded(envelope);
                break;
            case WRITE_COMPLETE:
                handleWriteComplete(envelope);
                break;
            case ERROR:
                handleError(envelope);
                break;
            default:
                handleUnknown(envelope);
        }
    }

    private void handleMsgSent(EventEnvelope envelope) {
        logEvent(envelope);
    }

    private void handleMsgForwarded(EventEnvelope envelope) {
        logEvent(envelope);
    }

    private void handleWriteComplete(EventEnvelope envelope) {
        logEvent(envelope);
        recordAck(envelope);
    }

    private void handleError(EventEnvelope envelope) {
        logEvent(envelope);
        recordError(envelope);
    }

    private void handleUnknown(EventEnvelope envelope) {
        logEvent(envelope);
    }

    private void logEvent(EventEnvelope envelope) {
        // log source and type
    }

    private void recordAck(EventEnvelope envelope) {
        AckEvent ack = new AckEvent();
        ack.setSessionId(envelope.getSourceId());
        ack.setSuccess(true);
        ackLog.add(ack);
    }

    private void recordError(EventEnvelope envelope) {
        ErrorEvent err = new ErrorEvent();
        err.setSourceService(envelope.getSourceId());
        err.setTimestamp(envelope.getTimestamp());
        errorLog.add(err);
    }

    public List<AckEvent> getAckLog() {
        return ackLog;
    }

    public List<ErrorEvent> getErrorLog() {
        return errorLog;
    }

    public int getProcessedCount() {
        return processedCount;
    }

    public boolean hasErrors() {
        return !errorLog.isEmpty();
    }
}
