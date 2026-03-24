package com.stresstest.client;

import com.stresstest.messages.Envelope;
import com.stresstest.messages.Header;
import com.stresstest.messages.RoutingKey;
import com.stresstest.messages.MessageBody;
import com.stresstest.events.EventEnvelope;
import com.stresstest.events.EventType;

import java.util.ArrayList;
import java.util.List;

/**
 * MessageClient — Java-side producer client.
 *
 * Builds Envelope messages and dispatches them to the C++ broker layer.
 * Uses proto-generated types (Envelope, Header, RoutingKey, MessageBody)
 * creating cross-language type bridge edges to the proto/C++ graph.
 */
public class MessageClient {

    private String clientId;
    private String defaultDestination;
    private List<Envelope> pendingMessages;
    private EventEnvelope lastEvent;
    private boolean connected;

    public MessageClient(String clientId, String defaultDestination) {
        this.clientId = clientId;
        this.defaultDestination = defaultDestination;
        this.pendingMessages = new ArrayList<>();
        this.connected = false;
    }

    public boolean connect() {
        this.connected = true;
        return connected;
    }

    public void disconnect() {
        flush();
        this.connected = false;
    }

    public Envelope buildEnvelope(String messageId, byte[] data, int priority) {
        RoutingKey routingKey = buildRoutingKey(defaultDestination, priority);
        Header header = buildHeader(messageId, routingKey);
        MessageBody body = buildBody(data);
        return assembleEnvelope(header, body);
    }

    private RoutingKey buildRoutingKey(String destination, int priority) {
        RoutingKey key = new RoutingKey();
        key.setDestination(destination);
        key.setPriority(priority);
        return key;
    }

    private Header buildHeader(String messageId, RoutingKey routingKey) {
        Header header = new Header();
        header.setMessageId(messageId);
        header.setRoutingKey(routingKey);
        header.setSourceId(clientId);
        header.setTimestamp(System.currentTimeMillis());
        return header;
    }

    private MessageBody buildBody(byte[] data) {
        MessageBody body = new MessageBody();
        body.setData(data);
        body.setChecksum(computeChecksum(data));
        return body;
    }

    private Envelope assembleEnvelope(Header header, MessageBody body) {
        Envelope envelope = new Envelope();
        envelope.setHeader(header);
        envelope.setBody(body);
        envelope.setSeqNum(pendingMessages.size());
        return envelope;
    }

    public boolean send(Envelope envelope) {
        if (!connected) {
            return false;
        }
        pendingMessages.add(envelope);
        return dispatchToNative(envelope);
    }

    private boolean dispatchToNative(Envelope envelope) {
        // Dispatches serialized envelope bytes to the C++ broker layer
        byte[] serialized = serializeEnvelope(envelope);
        return transmit(serialized, envelope.getHeader().getRoutingKey().getDestination());
    }

    private byte[] serializeEnvelope(Envelope envelope) {
        return envelope.toByteArray();
    }

    private boolean transmit(byte[] data, String destination) {
        // Bridge point to native transmit_message in producer/encoder.cc
        return data != null && data.length > 0;
    }

    public void onAck(EventEnvelope event) {
        this.lastEvent = event;
        if (event.getEventType() == EventType.MSG_SENT) {
            pruneDelivered();
        }
    }

    private void pruneDelivered() {
        pendingMessages.clear();
    }

    public void flush() {
        for (Envelope env : pendingMessages) {
            dispatchToNative(env);
        }
        pendingMessages.clear();
    }

    private long computeChecksum(byte[] data) {
        long sum = 0;
        for (byte b : data) {
            sum += b & 0xFF;
        }
        return sum;
    }

    public boolean isConnected() {
        return connected;
    }

    public int getPendingCount() {
        return pendingMessages.size();
    }

    public String getClientId() {
        return clientId;
    }
}
