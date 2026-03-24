package com.stresstest.android

import com.stresstest.events.EventEnvelope
import com.stresstest.events.EventType
import com.stresstest.events.AckEvent
import com.stresstest.events.ErrorEvent
import com.stresstest.client.EventSubscriber

/**
 * EventProcessor — Kotlin-side event processing layer.
 *
 * Tests: sealed class hierarchy, when expression (exhaustive),
 * interface with default implementation, extension functions,
 * lambda parameters, object expressions.
 * Cross-language: EventEnvelope, AckEvent, ErrorEvent (proto types),
 * EventSubscriber (Java class).
 */
sealed class ProcessingResult {
    data class Success(val eventType: EventType, val sourceId: String) : ProcessingResult()
    data class Failure(val reason: String, val event: EventEnvelope) : ProcessingResult()
    object Ignored : ProcessingResult()
}

interface EventFilter {
    fun accepts(event: EventEnvelope): Boolean

    fun and(other: EventFilter): EventFilter = object : EventFilter {
        override fun accepts(event: EventEnvelope): Boolean =
            this@EventFilter.accepts(event) && other.accepts(event)
    }
}

class EventProcessor(private val subscriber: EventSubscriber) {

    private val filters: MutableList<EventFilter> = mutableListOf()
    private val results: MutableList<ProcessingResult> = mutableListOf()

    fun addFilter(filter: EventFilter) {
        filters.add(filter)
    }

    fun process(event: EventEnvelope): ProcessingResult {
        if (!passesFilters(event)) {
            return ProcessingResult.Ignored
        }
        val result = route(event)
        results.add(result)
        subscriber.onEvent(event)
        return result
    }

    private fun passesFilters(event: EventEnvelope): Boolean {
        return filters.all { it.accepts(event) }
    }

    private fun route(event: EventEnvelope): ProcessingResult {
        return when (event.eventType) {
            EventType.MSG_SENT      -> handleMsgSent(event)
            EventType.MSG_FORWARDED -> handleMsgForwarded(event)
            EventType.WRITE_COMPLETE -> handleWriteComplete(event)
            EventType.ERROR         -> handleError(event)
            else                    -> ProcessingResult.Ignored
        }
    }

    private fun handleMsgSent(event: EventEnvelope): ProcessingResult {
        return ProcessingResult.Success(event.eventType, event.sourceId)
    }

    private fun handleMsgForwarded(event: EventEnvelope): ProcessingResult {
        return ProcessingResult.Success(event.eventType, event.sourceId)
    }

    private fun handleWriteComplete(event: EventEnvelope): ProcessingResult {
        recordAck(event)
        return ProcessingResult.Success(event.eventType, event.sourceId)
    }

    private fun handleError(event: EventEnvelope): ProcessingResult {
        return ProcessingResult.Failure("error event received", event)
    }

    private fun recordAck(event: EventEnvelope) {
        val ack = AckEvent()
        ack.sessionId = event.sourceId
        ack.success = true
    }

    fun getResults(): List<ProcessingResult> = results.toList()

    fun successCount(): Int = results.filterIsInstance<ProcessingResult.Success>().size

    fun failureCount(): Int = results.filterIsInstance<ProcessingResult.Failure>().size
}

// Extension function — tests: extension on sealed class
fun ProcessingResult.isTerminal(): Boolean = when (this) {
    is ProcessingResult.Failure -> true
    is ProcessingResult.Success -> false
    ProcessingResult.Ignored    -> false
}
