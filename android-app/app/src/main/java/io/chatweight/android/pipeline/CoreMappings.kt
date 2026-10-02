package io.chatweight.android.pipeline

import io.chatweight.android.database.entity.*
import io.chatweight.core.*

internal fun MessageEntity.toCore(): UnifiedMessage = UnifiedMessage(
    id = id, platform = Platform.valueOf(platform.uppercase()), conversationId = conversationId,
    direction = MessageDirection.valueOf(direction.uppercase()), type = MessageType.valueOf(messageType.uppercase()),
    messageTime = messageTime, capturedAt = capturedAt, fingerprint = fingerprint,
    accountId = accountId, personId = personId, senderId = senderId, senderName = senderName,
    text = text, voiceDurationMs = voiceDurationMs, replyToMessageId = replyToMessageId,
    captureSource = captureSource, confidence = confidence,
)

internal fun UnifiedMessage.toEntity(): MessageEntity = MessageEntity(
    id = id, platform = platform.name.lowercase(), accountId = accountId,
    conversationId = conversationId, personId = personId, senderId = senderId,
    senderName = senderName, direction = direction.name.lowercase(), messageType = type.name.lowercase(),
    text = text, messageTime = messageTime, capturedAt = capturedAt,
    voiceDurationMs = voiceDurationMs, replyToMessageId = replyToMessageId,
    fingerprint = fingerprint, captureSource = captureSource, confidence = confidence,
    rawJson = "{\"timestamp_semantics\":\"capture_observed_time\"}",
)

internal fun ChatSessionEntity.toCore(lastActor: ActorSide?): ChatSession = ChatSession(
    id = id, conversationId = conversationId, personId = primaryPersonId,
    startedAt = startedAt, lastMessageAt = lastMessageAt,
    initiatorSide = ActorSide.valueOf(initiatorSide.uppercase()), endedAt = endedAt,
    messageCount = messageCount.toInt(), incomingCount = incomingCount.toInt(),
    outgoingCount = outgoingCount.toInt(), turnCount = turnCount.toInt(), lastActorSide = lastActor,
)

internal fun ChatSession.toEntity(): ChatSessionEntity = ChatSessionEntity(
    id = id, conversationId = conversationId, primaryPersonId = personId,
    startedAt = startedAt, endedAt = endedAt, initiatorSide = initiatorSide.name.lowercase(),
    messageCount = messageCount.toLong(), incomingCount = incomingCount.toLong(),
    outgoingCount = outgoingCount.toLong(), turnCount = turnCount.toLong(),
    durationMs = (lastMessageAt - startedAt).coerceAtLeast(0L), lastMessageAt = lastMessageAt,
)

internal fun RelationshipProfileEntity.toCore(): RelationshipProfileState = RelationshipProfileState(
    personId = personId, type = RelationshipType.valueOf(relationshipType.uppercase()),
    customLabel = customLabel, expressionStage = ExpressionStage.fromLevel(expressionStage.toInt()),
    highestExpressionStage = ExpressionStage.fromLevel(highestExpressionStage.toInt()),
    expressionRaw = expressionRaw, expressionHeatRaw = expressionHeatRaw, heatUpdatedAt = heatUpdatedAt,
    manuallyConfirmedStage = manuallyConfirmedStage?.let { ExpressionStage.fromLevel(it.toInt()) },
    lastRelationshipEventAt = lastRelationshipEventAt, updatedAt = updatedAt,
)

internal fun RelationshipProfileState.toEntity(createdAt: Long): RelationshipProfileEntity = RelationshipProfileEntity(
    personId = personId, relationshipType = type.name.lowercase(), customLabel = customLabel,
    expressionStage = expressionStage.level.toLong(), highestExpressionStage = highestExpressionStage.level.toLong(),
    expressionRaw = expressionRaw, expressionHeatRaw = expressionHeatRaw, heatUpdatedAt = heatUpdatedAt,
    manuallyConfirmedStage = manuallyConfirmedStage?.level?.toLong(),
    lastRelationshipEventAt = lastRelationshipEventAt, engineVersion = 1L,
    createdAt = createdAt, updatedAt = updatedAt,
)
