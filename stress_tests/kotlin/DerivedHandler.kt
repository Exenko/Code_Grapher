package com.stresstest.android

import com.stresstest.legacy.LegacySession

/**
 * DerivedHandler — extends BaseHandler and tests super.method() resolution.
 *
 * Overrides handle() and calls super.handle(session) and super.cleanup()
 * to exercise the super.method() call resolution path in the Kotlin parser.
 */
class DerivedHandler : BaseHandler() {

    private var filterCount: Int = 0

    override fun handle(session: LegacySession) {
        // Call super.handle(session) — should resolve to BaseHandler.handle()
        super.handle(session)
        filterCount++
    }

    fun clearAll() {
        // Call super.cleanup() — should resolve to BaseHandler.cleanup()
        super.cleanup()
        filterCount = 0
    }

    fun getFilterCount(): Int = filterCount
}
