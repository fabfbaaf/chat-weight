package io.chatweight.android.ingest

import io.chatweight.core.MessageDirection
import io.chatweight.core.MessageType
import io.chatweight.core.Platform
import io.chatweight.core.UnifiedMessage
import java.util.UUID

data class CapturedLine(val side: String, val text: String, val senderName: String? = null)
data class ScreenCursor(val keys: List<String>, val nextSequence: Long)
data class NormalizedCapture(
    val conversationId: String,
    val conversationTitle: String,
    val conversationType: String,
    val primaryPersonId: String?,
    val messages: List<UnifiedMessage>,
    val cursor: ScreenCursor,
)

/** Turns one visible screen into only its new tail, without treating repeated text as one message. */
object MessageNormalizer {
    fun conversationId(platform: Platform, title: String): String =
        "${platform.name.lowercase()}:android:conversation:${MessageFingerprint.sha256(title.trim().lowercase()).take(24)}"

    fun normalize(
        platform: Platform,
        title: String,
        visible: List<CapturedLine>,
        previous: ScreenCursor?,
        observedAt: Long,
        source: String = "android_accessibility",
        primeExisting: Boolean = true,
    ): NormalizedCapture {
        val cleanTitle = title.trim()
        require(cleanTitle.isNotEmpty()) { "A stable visible conversation title is required" }
        val cid = conversationId(platform, cleanTitle)
        val lines = visible.map { it.copy(text = it.text.trim(), senderName = it.senderName?.trim()) }
            .filter { it.text.isNotBlank() && it.side in setOf("me", "other") }
        val keys = lines.map { "${it.side}\u001f${it.senderName.orEmpty()}\u001f${it.text}" }
        val group = lines.any { it.side == "other" && !it.senderName.isNullOrBlank() } ||
            Regex("[（(]\\d+[)）]$").containsMatchIn(cleanTitle)
        val kind = if (group) "group" else "private"
        val primary = if (group) null else "${platform.name.lowercase()}:android:person:${MessageFingerprint.sha256(cleanTitle.lowercase()).take(24)}"
        val overlap = when {
            previous == null -> if (primeExisting) keys.size else 0
            previous.keys == keys -> keys.size
            else -> (minOf(previous.keys.size, keys.size) downTo 1)
                .firstOrNull { n -> previous.keys.takeLast(n) == keys.take(n) } ?: keys.size
        }
        var seq = previous?.nextSequence ?: 0L
        val newMessages = lines.drop(overlap).mapIndexed { index, line ->
            val direction = if (line.side == "me") MessageDirection.OUTGOING else MessageDirection.INCOMING
            val pid = if (group) {
                line.senderName?.takeIf { direction == MessageDirection.INCOMING }?.let {
                    "${platform.name.lowercase()}:android:group-member:${MessageFingerprint.sha256(cid + "\u0000" + it).take(24)}"
                }
            } else primary
            val fingerprint = MessageFingerprint.sha256(
                listOf(platform.name, cid, line.side, line.senderName.orEmpty(), line.text,
                    seq.toString(), (observedAt / 30_000L).toString()).joinToString("\u001f")
            )
            seq += 1
            UnifiedMessage(
                id = UUID.nameUUIDFromBytes(fingerprint.toByteArray(Charsets.UTF_8)).toString(),
                platform = platform,
                conversationId = cid,
                personId = pid,
                senderId = if (direction == MessageDirection.OUTGOING) "self" else pid,
                senderName = if (direction == MessageDirection.OUTGOING) "我" else line.senderName ?: if (group) null else cleanTitle,
                direction = direction,
                type = MessageType.TEXT,
                text = line.text,
                messageTime = observedAt + index,
                capturedAt = observedAt + index,
                fingerprint = fingerprint,
                captureSource = source,
                confidence = if (source.contains("ocr")) 0.90 else 0.98,
            )
        }
        return NormalizedCapture(cid, cleanTitle, kind, primary, newMessages, ScreenCursor(keys, seq))
    }

}
