package com.stresstest.android

import com.stresstest.messages.Envelope
import com.stresstest.messages.Header
import com.stresstest.messages.RoutingKey
import com.stresstest.client.MessageClient

/**
 * BrokerConnection — Kotlin wrapper around the Java MessageClient.
 *
 * Tests: data class, companion object (static factory), secondary constructor,
 * property delegation, null safety, string templates, named parameters.
 * Cross-language: uses Envelope, Header, RoutingKey (proto types) and
 * MessageClient (Java class) — bridge edges to Java/Proto layers.
 */
data class ConnectionConfig(
    val host: String,
    val port: Int,
    val clientId: String,
    val maxRetries: Int = 3,
    val timeoutMs: Long = 5000L
)

class BrokerConnection(private val config: ConnectionConfig) {

    private var client: MessageClient = MessageClient(config.clientId, "${config.host}:${config.port}")
    private var retryCount: Int = 0
    private var lastEnvelope: Envelope? = null

    companion object {
        fun create(host: String, port: Int, clientId: String): BrokerConnection {
            val config = ConnectionConfig(host = host, port = port, clientId = clientId)
            return BrokerConnection(config)
        }

        fun createWithDefaults(clientId: String): BrokerConnection {
            return create("localhost", 9090, clientId)
        }
    }

    fun connect(): Boolean {
        retryCount = 0
        return client.connect()
    }

    fun disconnect() {
        client.disconnect()
        retryCount = 0
    }

    fun sendEnvelope(messageId: String, data: ByteArray, priority: Int = 5): Boolean {
        val envelope = buildEnvelope(messageId, data, priority)
        lastEnvelope = envelope
        return client.send(envelope)
    }

    private fun buildEnvelope(messageId: String, data: ByteArray, priority: Int): Envelope {
        return client.buildEnvelope(messageId, data, priority)
    }

    fun retry(): Boolean {
        if (retryCount >= config.maxRetries) return false
        retryCount++
        val env = lastEnvelope ?: return false
        return client.send(env)
    }

    fun getStatus(): String {
        return if (client.isConnected) {
            "connected (pending=${client.pendingCount})"
        } else {
            "disconnected (retries=$retryCount/${config.maxRetries})"
        }
    }

    fun getPendingCount(): Int = client.pendingCount

    fun isConnected(): Boolean = client.isConnected
}
