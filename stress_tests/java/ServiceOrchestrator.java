package com.stresstest.client;

import com.stresstest.events.EventEnvelope;
import com.stresstest.events.EventType;
import com.stresstest.legacy.LegacySession;

/**
 * ServiceOrchestrator — Java entry point.
 *
 * Wires MessageClient, EventSubscriber, and LegacyAdapter together.
 * Represents the Java service layer coordinating message flow to the C++ backend.
 * Static main() makes this the detected entry point for graph analysis.
 */
public class ServiceOrchestrator {

    private MessageClient client;
    private EventSubscriber subscriber;
    private LegacyAdapter legacyAdapter;
    private boolean running;

    public ServiceOrchestrator(String serviceId, String brokerAddress) {
        this.client = new MessageClient(serviceId, brokerAddress);
        this.subscriber = new EventSubscriber();
        this.legacyAdapter = new LegacyAdapter(client);
        this.running = false;
    }

    public void start() {
        boolean connected = client.connect();
        if (!connected) {
            return;
        }
        registerSubscriptions();
        running = true;
    }

    public void stop() {
        running = false;
        client.disconnect();
    }

    private void registerSubscriptions() {
        subscriber.subscribe(EventType.MSG_SENT,      e -> subscriber.onEvent(e));
        subscriber.subscribe(EventType.MSG_FORWARDED, e -> subscriber.onEvent(e));
        subscriber.subscribe(EventType.WRITE_COMPLETE, e -> onAckReceived(e));
        subscriber.subscribe(EventType.ERROR,         e -> onErrorReceived(e));
    }

    private void onAckReceived(EventEnvelope event) {
        client.onAck(event);
        subscriber.onEvent(event);
    }

    private void onErrorReceived(EventEnvelope event) {
        subscriber.onEvent(event);
        if (subscriber.hasErrors()) {
            handleDegradedMode();
        }
    }

    private void handleDegradedMode() {
        client.flush();
    }

    public boolean sendMessage(String messageId, byte[] payload, int priority) {
        if (!running) {
            return false;
        }
        var envelope = client.buildEnvelope(messageId, payload, priority);
        return client.send(envelope);
    }

    public boolean adaptLegacySession(LegacySession session) {
        if (!running) {
            return false;
        }
        return legacyAdapter.adaptSession(session);
    }

    public int getPendingCount() {
        return client.getPendingCount();
    }

    public boolean isRunning() {
        return running;
    }

    public EventSubscriber getSubscriber() {
        return subscriber;
    }

    public static void main(String[] args) {
        String serviceId    = args.length > 0 ? args[0] : "java-client-1";
        String brokerAddr   = args.length > 1 ? args[1] : "localhost:9090";

        ServiceOrchestrator orchestrator = new ServiceOrchestrator(serviceId, brokerAddr);
        orchestrator.start();

        if (!orchestrator.isRunning()) {
            System.exit(1);
        }

        byte[] testPayload = "hello broker".getBytes();
        orchestrator.sendMessage("msg-001", testPayload, 5);

        System.out.println("Pending: " + orchestrator.getPendingCount());
        System.out.println("Events processed: " + orchestrator.getSubscriber().getProcessedCount());

        orchestrator.stop();
    }
}
