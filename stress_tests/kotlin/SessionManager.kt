package com.stresstest.android

import com.stresstest.legacy.LegacySession
import com.stresstest.client.LegacyAdapter

/**
 * SessionManager — manages LegacySession lifecycle on the Android side.
 *
 * Tests: generic class, interface implementation, suspend fun stubs (coroutine marker),
 * lateinit var, object declaration (singleton), enum class,
 * higher-order functions (forEach, map, filter).
 * Cross-language: LegacySession (proto type), LegacyAdapter (Java class).
 */
enum class SessionState {
    PENDING, ACTIVE, DRAINING, CLOSED
}

interface SessionLifecycle<T> {
    fun onOpen(session: T)
    fun onClose(session: T)
    fun onError(session: T, reason: String)
}

object SessionRegistry {
    private val sessions: MutableMap<String, SessionState> = mutableMapOf()

    fun register(id: String) {
        sessions[id] = SessionState.PENDING
    }

    fun transition(id: String, state: SessionState) {
        sessions[id] = state
    }

    fun stateOf(id: String): SessionState? = sessions[id]

    fun activeIds(): List<String> =
        sessions.filter { it.value == SessionState.ACTIVE }.keys.toList()

    fun clear() {
        sessions.clear()
    }
}

class SessionManager(
    private val adapter: LegacyAdapter,
    private val lifecycle: SessionLifecycle<LegacySession>
) {

    private val activeSessions: MutableList<LegacySession> = mutableListOf()
    private var drainedCount: Int = 0

    fun open(session: LegacySession) {
        SessionRegistry.register(session.sessionId)
        SessionRegistry.transition(session.sessionId, SessionState.ACTIVE)
        activeSessions.add(session)
        lifecycle.onOpen(session)
    }

    fun close(session: LegacySession) {
        SessionRegistry.transition(session.sessionId, SessionState.CLOSED)
        activeSessions.remove(session)
        lifecycle.onClose(session)
    }

    fun drain(session: LegacySession): Boolean {
        SessionRegistry.transition(session.sessionId, SessionState.DRAINING)
        val ok = adapter.adaptSession(session)
        if (ok) {
            drainedCount++
            close(session)
        } else {
            lifecycle.onError(session, "drain failed")
        }
        return ok
    }

    fun drainAll(): Int {
        val snapshot = activeSessions.toList()
        var count = 0
        snapshot.forEach { session ->
            if (drain(session)) count++
        }
        return count
    }

    suspend fun drainAsync(session: LegacySession): Boolean {
        return drain(session)
    }

    fun getActiveCount(): Int = activeSessions.size

    fun getDrainedCount(): Int = drainedCount

    fun getActiveSessions(): List<LegacySession> = activeSessions.toList()

    fun summarize(): Map<String, Int> = mapOf(
        "active"  to getActiveCount(),
        "drained" to getDrainedCount()
    )
}
