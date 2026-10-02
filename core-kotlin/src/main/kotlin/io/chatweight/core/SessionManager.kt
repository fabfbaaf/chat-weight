package io.chatweight.core

import java.util.UUID

/** Stateless session transition; callers persist [ChatSession] after each message. */
object SessionManager {
    const val GAP_MS = 30L * 60L * 1000L

    data class Result(val session: ChatSession, val isNew: Boolean)

    fun ingest(message: UnifiedMessage, previous: ChatSession?): Result {
        val isNew = previous == null || message.messageTime - previous.lastMessageAt >= GAP_MS
        val actor = message.actorSide
        val base = if (isNew) ChatSession(
            id = UUID.randomUUID().toString(),
            conversationId = message.conversationId,
            personId = message.personId,
            startedAt = message.messageTime,
            lastMessageAt = message.messageTime,
            initiatorSide = actor,
        ) else previous!!
        return Result(base.copy(
            personId = base.personId ?: message.personId,
            messageCount = base.messageCount + 1,
            incomingCount = base.incomingCount + if (message.direction == MessageDirection.INCOMING) 1 else 0,
            outgoingCount = base.outgoingCount + if (message.direction == MessageDirection.OUTGOING) 1 else 0,
            turnCount = base.turnCount + if (base.lastActorSide != null && base.lastActorSide != actor && actor != ActorSide.BOTH) 1 else 0,
            lastActorSide = actor,
            lastMessageAt = message.messageTime,
        ), isNew)
    }
}
