package io.chatweight.android.capture

/** Recheck visually identical geometry: message text may change without moving bubbles. */
object OcrRefreshPolicy {
    const val MIN_SAME_SCREEN_INTERVAL_MS = 2_500L

    fun shouldCapture(signature: String, previousSignature: String, now: Long, lastAttemptAt: Long): Boolean =
        signature != previousSignature || now - lastAttemptAt >= MIN_SAME_SCREEN_INTERVAL_MS
}
