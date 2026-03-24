package com.stresstest.client;

import com.stresstest.legacy.LegacyEvent_Proto;
import com.stresstest.legacy.LegacySession;
import com.stresstest.legacy.LegacyEventType;
import com.stresstest.messages.Envelope;
import com.stresstest.messages.MessageBody;

import java.util.ArrayList;
import java.util.List;

/**
 * LegacyAdapter — bridges LegacyEvent_Proto/LegacySession (legacy.proto)
 * to current Envelope format (messages.proto), then forwards via MessageClient.
 *
 * Mirrors the C++ LegacyEvent_CC → Envelope conversion path in
 * producer/legacy_encoder.cc. Creates cross-language bridge edges:
 *   LegacyEvent_Proto → LegacyEvent_CC (via shared type name in legacy.proto)
 *   LegacySession → Envelope (conversion path)
 */
public class LegacyAdapter {

    private MessageClient client;
    private List<LegacySession> sessionLog;
    private int convertedCount;
    private int droppedCount;

    public LegacyAdapter(MessageClient client) {
        this.client = client;
        this.sessionLog = new ArrayList<>();
        this.convertedCount = 0;
        this.droppedCount = 0;
    }

    public boolean adaptSession(LegacySession session) {
        if (!validateSession(session)) {
            droppedCount++;
            return false;
        }
        sessionLog.add(session);
        return processSessionEvents(session);
    }

    private boolean validateSession(LegacySession session) {
        return session != null
            && session.getSessionId() != null
            && !session.getEventsList().isEmpty();
    }

    private boolean processSessionEvents(LegacySession session) {
        boolean allOk = true;
        for (LegacyEvent_Proto event : session.getEventsList()) {
            boolean ok = adaptEvent(session.getSessionId(), event);
            if (!ok) {
                allOk = false;
            }
        }
        return allOk;
    }

    private boolean adaptEvent(String sessionId, LegacyEvent_Proto event) {
        if (shouldDrop(event)) {
            droppedCount++;
            return false;
        }
        Envelope envelope = convertToEnvelope(sessionId, event);
        convertedCount++;
        return client.send(envelope);
    }

    private boolean shouldDrop(LegacyEvent_Proto event) {
        return event.getEventType() == LegacyEventType.LEGACY_UNKNOWN;
    }

    private Envelope convertToEnvelope(String sessionId, LegacyEvent_Proto event) {
        MessageBody body = extractBody(event);
        byte[] data = body.getData().toByteArray();
        return client.buildEnvelope(sessionId + ":" + event.getVersion(), data, priorityFor(event));
    }

    private MessageBody extractBody(LegacyEvent_Proto event) {
        return event.getPayload();
    }

    private int priorityFor(LegacyEvent_Proto event) {
        switch (event.getEventType()) {
            case LEGACY_CONTROL:   return 10;
            case LEGACY_HEARTBEAT: return 1;
            case LEGACY_DATA:      return 5;
            default:               return 0;
        }
    }

    public int getConvertedCount() {
        return convertedCount;
    }

    public int getDroppedCount() {
        return droppedCount;
    }

    public List<LegacySession> getSessionLog() {
        return sessionLog;
    }
}
