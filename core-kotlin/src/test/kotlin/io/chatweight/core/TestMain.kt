package io.chatweight.core

fun main() {
    check(DecayEngine.rawToScore(0.0) == 0.0)
    check(DecayEngine.rawToScore(40.0) > 80.0)

    val msg = UnifiedMessage(
        id = "m1", platform = Platform.WECHAT, conversationId = "c1",
        direction = MessageDirection.OUTGOING, type = MessageType.TEXT,
        messageTime = 1_000L, capturedAt = 1_000L, fingerprint = "fp",
        personId = "p1", text = "其实我挺喜欢你的"
    )
    val events = RelationshipEventDetector().detect(RelationshipDetectionContext(msg))
    val direct = events.first { it.eventType == RelationshipEventType.DIRECT_LIKE_EXPRESSION }
    check(direct.confirmationPolicy == ConfirmationPolicy.USER_REVIEW)
    check(direct.status == CandidateStatus.PENDING)

    val profile = RelationshipProfileState(
        personId = "p1", type = RelationshipType.CRUSH,
        expressionRaw = 90.0, expressionStage = ExpressionStage.OBVIOUS_CARE,
        highestExpressionStage = ExpressionStage.OBVIOUS_CARE, heatUpdatedAt = 1000L,
    )
    val affection = RelationshipEventCandidate(
        id = "e1", personId = "p1", conversationId = "c1", actorSide = ActorSide.SELF,
        eventType = RelationshipEventType.LIGHT_MISSING_EXPRESSION,
        source = DetectionSource.LOCAL_SEMANTIC_RULE, confidence = 1.0,
        confirmationPolicy = ConfirmationPolicy.HIGH_CONFIDENCE_ONLY,
        status = CandidateStatus.CONFIRMED, eventTime = 2000L,
    )
    val updated = RelationshipEngine.apply(
        profile, affection,
        RelationshipStageEvidence(10, 10, 4, hasAffectionEvent = true)
    )
    check(updated.expressionStage == ExpressionStage.LIGHT_AFFECTION)
    check(updated.expressionStage.level < ExpressionStage.DIRECT_EXPRESSION.level)

    println("Kotlin core tests: OK")
}
