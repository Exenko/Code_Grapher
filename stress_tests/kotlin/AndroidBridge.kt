package com.stresstest.android

import com.stresstest.client.MessageClient
import com.stresstest.client.EventSubscriber
import com.stresstest.client.LegacyAdapter
import com.stresstest.events.EventEnvelope
import com.stresstest.events.EventType
import com.stresstest.legacy.LegacySession

/**
 * AndroidBridge — Android Application subclass entry point.
 *
 * Tests: open class (inheritable), init block, property initializers,
 * lazy delegation, companion object with const, override fun,
 * lambda with receiver.
 * Mirrors the real PowerGlide MainApplication.kt pattern.
 * Wires BrokerConnection, EventProcessor, SessionManager together —
 * cross-file calls to all three Kotlin classes plus Java layer.
 */
open class AndroidBridge : ApplicationBase() {

    companion object {
        const val SERVICE_ID = "android-bridge-1"
        const val BROKER_HOST = "localhost"
        const val BROKER_PORT = 9090

        @Volatile
        private var instance: AndroidBridge? = null

        fun getInstance(): AndroidBridge? = instance
    }

    private lateinit var connection: BrokerConnection
    private lateinit var processor: EventProcessor
    private lateinit var sessionManager: SessionManager

    private val eventSubscriber: EventSubscriber by lazy {
        EventSubscriber()
    }

    private val legacyAdapter: LegacyAdapter by lazy {
        LegacyAdapter(MessageClient(SERVICE_ID, "$BROKER_HOST:$BROKER_PORT"))
    }

    init {
        instance = this
    }

    override fun onCreate() {
        super.onCreate()
        initConnection()
        initProcessor()
        initSessionManager()
        registerEventHandlers()
    }

    private fun initConnection() {
        connection = BrokerConnection.create(BROKER_HOST, BROKER_PORT, SERVICE_ID)
        connection.connect()
    }

    private fun initProcessor() {
        processor = EventProcessor(eventSubscriber)
        processor.addFilter(object : EventFilter {
            override fun accepts(event: EventEnvelope): Boolean =
                event.eventType != EventType.UNKNOWN
        })
    }

    private fun initSessionManager() {
        sessionManager = SessionManager(
            adapter = legacyAdapter,
            lifecycle = object : SessionLifecycle<LegacySession> {
                override fun onOpen(session: LegacySession) = Unit
                override fun onClose(session: LegacySession) = Unit
                override fun onError(session: LegacySession, reason: String) {
                    handleSessionError(session, reason)
                }
            }
        )
    }

    private fun registerEventHandlers() {
        eventSubscriber.subscribe(EventType.MSG_SENT)      { e -> processor.process(e) }
        eventSubscriber.subscribe(EventType.MSG_FORWARDED) { e -> processor.process(e) }
        eventSubscriber.subscribe(EventType.WRITE_COMPLETE){ e -> processor.process(e) }
        eventSubscriber.subscribe(EventType.ERROR)         { e -> processor.process(e) }
    }

    fun sendMessage(messageId: String, data: ByteArray, priority: Int = 5): Boolean {
        if (!connection.isConnected()) return false
        return connection.sendEnvelope(messageId, data, priority)
    }

    fun adaptLegacySession(session: LegacySession): Boolean {
        return sessionManager.drain(session)
    }

    override fun onTerminate() {
        super.onTerminate()
        sessionManager.drainAll()
        connection.disconnect()
        SessionRegistry.clear()
    }

    private fun handleSessionError(session: LegacySession, reason: String) {
        connection.retry()
    }

    fun getStatus(): String = connection.getStatus()

    fun getStats(): Map<String, Int> = sessionManager.summarize()
}

/**
 * ApplicationBase — stub base class (mirrors android.app.Application in real Android).
 * Keeps corpus self-contained without Android SDK dependency.
 */
open class ApplicationBase {
    open fun onCreate() {}
    open fun onTerminate() {}
}
