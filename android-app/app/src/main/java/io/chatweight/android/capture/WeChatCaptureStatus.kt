package io.chatweight.android.capture

import android.content.Context

/** Minimal on-device diagnostics. Stores status codes only, never chat text or screenshots. */
object WeChatCaptureStatus {
    private const val NAME = "wechat_capture_status"
    private const val STATUS = "status"
    private const val AT = "at"
    private const val LAST_MESSAGE = "last_message"
    private const val LAST_EVENT = "last_event"

    fun markEvent(context: Context) {
        val now = System.currentTimeMillis()
        val prefs = context.getSharedPreferences(NAME, Context.MODE_PRIVATE)
        val edit = prefs.edit().putLong(LAST_EVENT, now)
        if (!prefs.contains(STATUS)) edit.putString(STATUS, "收到微信无障碍事件").putLong(AT, now)
        edit.apply()
    }

    fun mark(context: Context, status: String, inserted: Boolean = false) {
        val now = System.currentTimeMillis()
        context.getSharedPreferences(NAME, Context.MODE_PRIVATE).edit()
            .putString(STATUS, status).putLong(AT, now)
            .apply()
        if (inserted) context.getSharedPreferences(NAME, Context.MODE_PRIVATE).edit()
            .putLong(LAST_MESSAGE, now).apply()
    }

    fun read(context: Context): Triple<String, Long, Long> {
        val prefs = context.getSharedPreferences(NAME, Context.MODE_PRIVATE)
        return Triple(prefs.getString(STATUS, "尚未收到微信采集事件").orEmpty(),
            prefs.getLong(AT, 0L), prefs.getLong(LAST_MESSAGE, 0L))
    }
}
