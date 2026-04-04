package com.stresstest.android

import com.stresstest.legacy.LegacySession

/**
 * BaseHandler — base open class for testing super.method() resolution in Kotlin.
 *
 * Defines handle(session: LegacySession) and cleanup() methods that will be called
 * via super. from DerivedHandler.
 */
open class BaseHandler {

    protected var sessionCount: Int = 0

    open fun handle(session: LegacySession) {
        if (session != null) {
            sessionCount++
        }
    }

    open fun cleanup() {
        sessionCount = 0
    }

    fun getSessionCount(): Int = sessionCount
}
