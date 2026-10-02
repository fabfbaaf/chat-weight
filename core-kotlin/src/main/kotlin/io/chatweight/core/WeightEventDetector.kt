package io.chatweight.core

import java.util.UUID

/** Shared event detection used by Android; scoring remains in [WeightEngine]. */
object WeightEventDetector {
    fun detect(
        current: UnifiedMessage,
        previous: UnifiedMessage?,
        session: ChatSession,
        isNewSession: Boolean,
        recent: List<UnifiedMessage> = emptyList(),
        medianTextLength: Double = 12.0,
    ): List<DetectedWeightEvent> {
        if (current.personId == null || current.direction == MessageDirection.SYSTEM) return emptyList()
        val out = mutableListOf<DetectedWeightEvent>()
        fun emit(type: WeightEventType) {
            if (type !in WeightRuleRegistry.rules) return
            val key = "${current.id}:${type.name}"
            out += DetectedWeightEvent(
                id = UUID.nameUUIDFromBytes(key.toByteArray(Charsets.UTF_8)).toString(),
                personId = current.personId,
                conversationId = current.conversationId,
                actor = current.actorSide,
                eventType = type,
                eventTime = current.messageTime,
                sessionId = session.id,
                sourceMessageIds = listOf(current.id),
            )
        }
        if (isNewSession) emit(WeightEventType.SESSION_START)
        if (previous != null && previous.actorSide != current.actorSide && previous.actorSide != ActorSide.BOTH) {
            val gap = current.messageTime - previous.messageTime
            when {
                gap in 0L..60_000L -> emit(WeightEventType.REPLY_WITHIN_1M)
                gap <= 5 * 60_000 -> emit(WeightEventType.REPLY_WITHIN_5M)
                gap <= 15 * 60_000 -> emit(WeightEventType.REPLY_WITHIN_15M)
                gap <= 60 * 60_000 -> emit(WeightEventType.REPLY_WITHIN_60M)
                gap <= 6 * 60 * 60_000 -> emit(WeightEventType.REPLY_WITHIN_6H)
            }
        }
        if (previous?.actorSide == current.actorSide) {
            val gap = current.messageTime - previous.messageTime
            if (gap in (5L * 60_000L) until SessionManager.GAP_MS) emit(WeightEventType.FOLLOW_UP_WITHOUT_REPLY)
        }
        val burst = recent.count { it.actorSide == current.actorSide && current.messageTime - it.messageTime in 0L..90_000L } + 1
        if (burst == 2) emit(WeightEventType.BURST_2_3)
        if (burst == 4) emit(WeightEventType.BURST_4_PLUS)
        val tail = (recent + current).takeLast(8).asReversed()
            .takeWhile { it.actorSide == current.actorSide && !it.text.isNullOrBlank() && it.text!!.length <= 6 }
        if (tail.size == 3) emit(WeightEventType.SHORT_REPLY_CHAIN_3)
        if (tail.size == 5) emit(WeightEventType.SHORT_REPLY_CHAIN_5)
        if (!current.text.isNullOrBlank() && medianTextLength > 0) {
            val ratio = current.text!!.trim().length / medianTextLength
            when {
                ratio >= 6 -> emit(WeightEventType.LONG_REPLY_6X)
                ratio >= 3 -> emit(WeightEventType.LONG_REPLY_3X)
                ratio >= 1.5 -> emit(WeightEventType.LONG_REPLY_1_5X)
            }
        }
        when (current.type) {
            MessageType.IMAGE -> emit(WeightEventType.SEND_IMAGE)
            MessageType.STICKER -> emit(WeightEventType.SEND_STICKER)
            MessageType.LINK -> emit(WeightEventType.SEND_LINK)
            MessageType.FILE -> emit(WeightEventType.SEND_FILE)
            else -> Unit
        }
        for ((turns, type) in listOf(
            30 to WeightEventType.SESSION_30_TURNS,
            15 to WeightEventType.SESSION_15_TURNS,
            8 to WeightEventType.SESSION_8_TURNS,
            4 to WeightEventType.SESSION_4_TURNS,
        )) if (session.turnCount == turns) { emit(type); break }
        return out
    }
}
