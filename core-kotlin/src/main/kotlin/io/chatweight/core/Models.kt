package io.chatweight.core

enum class Platform { WECHAT, QQ }
enum class MessageDirection { INCOMING, OUTGOING, SYSTEM }
enum class MessageType { TEXT, IMAGE, STICKER, VOICE, VIDEO, FILE, LINK, SYSTEM, UNKNOWN }
enum class ActorSide { SELF, OTHER, BOTH }
enum class WeightDimension { INITIATIVE, RESPONSE, EFFORT, CONTINUITY, FREQUENCY }

enum class WeightEventType {
    SESSION_START, FOLLOW_UP_WITHOUT_REPLY, DIRECT_MENTION, DIRECT_QUOTE, GROUP_GENERAL_MESSAGE,
    REPLY_WITHIN_1M, REPLY_WITHIN_5M, REPLY_WITHIN_15M, REPLY_WITHIN_60M, REPLY_WITHIN_6H,
    DIRECT_REPLY, QUESTION_UNANSWERED_24H, MULTIPLE_QUESTIONS_UNANSWERED,
    LONG_REPLY_1_5X, LONG_REPLY_3X, LONG_REPLY_6X, BURST_2_3, BURST_4_PLUS,
    SEND_IMAGE, SEND_STICKER, SEND_LINK, SEND_FILE, SEND_VOICE_10_30S, SEND_VOICE_30_60S,
    SEND_VOICE_60S_PLUS, SHORT_REPLY_CHAIN_3, SHORT_REPLY_CHAIN_5,
    SESSION_4_TURNS, SESSION_8_TURNS, SESSION_15_TURNS, SESSION_30_TURNS,
    SESSION_20_MIN, SESSION_60_MIN, SESSION_120_MIN,
    ACTIVE_DAY, ACTIVE_STREAK_3D, ACTIVE_STREAK_7D, ACTIVE_STREAK_14D, ACTIVE_3_DAYS_WEEK, ACTIVE_5_DAYS_WEEK
}

enum class RelationshipType { FRIEND, CRUSH, PARTNER, FAMILY, COLLEAGUE, CUSTOM }

enum class ExpressionStage(val level: Int) {
    NORMAL_CONTACT(0), FAMILIARITY(1), APPROACHING(2), OBVIOUS_CARE(3),
    LIGHT_AFFECTION(4), DIRECT_EXPRESSION(5), RELATIONSHIP_CONFIRMED(6);

    companion object {
        fun fromLevel(level: Int): ExpressionStage = entries.firstOrNull { it.level == level } ?: NORMAL_CONTACT
    }
}

enum class RelationshipEventCategory { FAMILIARITY, APPROACH, CARE, AFFECTION, DIRECT_EXPRESSION, RELATIONSHIP, RETREAT }

enum class RelationshipEventType {
    PERSONAL_TOPIC, PERSONAL_QUESTION, SELF_DISCLOSURE, SHARED_EXPERIENCE,
    INITIATE_PRIVATE_CHAT, TARGETED_SHARING, CONTINUE_CONVERSATION, INITIATE_VOICE_CALL, INITIATE_ACTIVITY, INITIATE_MEETUP,
    CHECK_IN, REMEMBER_AND_FOLLOW_UP, EMOTIONAL_SUPPORT, PRACTICAL_SUPPORT, SAFETY_CONCERN, SPECIAL_DATE_ATTENTION,
    SPECIAL_COMPLIMENT, SPECIAL_NICKNAME, LIGHT_FLIRT, LIGHT_MISSING_EXPRESSION, CARE_EXPRESSION,
    DEPENDENCY_EXPRESSION, SPECIAL_IMPORTANCE_EXPRESSION,
    DIRECT_LIKE_EXPRESSION, DIRECT_ROMANTIC_INTENT, PURSUIT_EXPRESSION,
    MUTUAL_AFFECTION_EXPRESSION, POSSIBLE_RELATIONSHIP_CONFIRMED, RELATIONSHIP_CONFIRMED,
    FRIEND_ONLY_EXPRESSION, WITHDRAW_AFFECTION, STOP_PURSUIT, RELATIONSHIP_ENDED
}

enum class DetectionSource { LOCAL_FACT, LOCAL_SEMANTIC_RULE, SEMANTIC_MODEL, MANUAL }
enum class ConfirmationPolicy { AUTO_APPLY, HIGH_CONFIDENCE_ONLY, USER_REVIEW, MANUAL_ONLY }
enum class CandidateStatus { PENDING, CONFIRMED, REJECTED, AUTO_CONFIRMED }

data class UnifiedMessage(
    val id: String,
    val platform: Platform,
    val conversationId: String,
    val direction: MessageDirection,
    val type: MessageType,
    val messageTime: Long,
    val capturedAt: Long,
    val fingerprint: String,
    val accountId: String? = null,
    val personId: String? = null,
    val senderId: String? = null,
    val senderName: String? = null,
    val text: String? = null,
    val voiceDurationMs: Long? = null,
    val replyToMessageId: String? = null,
    val captureSource: String = "adapter",
    val confidence: Double = 1.0,
) {
    val actorSide: ActorSide
        get() = when (direction) {
            MessageDirection.OUTGOING -> ActorSide.SELF
            MessageDirection.INCOMING -> ActorSide.OTHER
            MessageDirection.SYSTEM -> ActorSide.BOTH
        }
}

data class ChatSession(
    val id: String,
    val conversationId: String,
    val startedAt: Long,
    val lastMessageAt: Long,
    val initiatorSide: ActorSide,
    val personId: String? = null,
    val endedAt: Long? = null,
    val messageCount: Int = 0,
    val incomingCount: Int = 0,
    val outgoingCount: Int = 0,
    val turnCount: Int = 0,
    val lastActorSide: ActorSide? = null,
)

data class DetectedWeightEvent(
    val id: String,
    val personId: String,
    val conversationId: String,
    val actor: ActorSide,
    val eventType: WeightEventType,
    val eventTime: Long,
    val sessionId: String? = null,
    val sourceMessageIds: List<String> = emptyList(),
    val confidence: Double = 1.0,
    val metadata: Map<String, String> = emptyMap(),
)

data class RelationshipEventCandidate(
    val id: String,
    val personId: String,
    val conversationId: String,
    val actorSide: ActorSide,
    val eventType: RelationshipEventType,
    val source: DetectionSource,
    val confidence: Double,
    val confirmationPolicy: ConfirmationPolicy,
    val status: CandidateStatus,
    val eventTime: Long,
    val sessionId: String? = null,
    val sourceMessageIds: List<String> = emptyList(),
    val evidenceText: String? = null,
    val reasonCode: String = "",
    val metadata: Map<String, String> = emptyMap(),
)

data class RelationshipProfileState(
    val personId: String,
    val type: RelationshipType = RelationshipType.FRIEND,
    val customLabel: String? = null,
    val expressionStage: ExpressionStage = ExpressionStage.NORMAL_CONTACT,
    val highestExpressionStage: ExpressionStage = ExpressionStage.NORMAL_CONTACT,
    val expressionRaw: Double = 0.0,
    val expressionHeatRaw: Double = 0.0,
    val heatUpdatedAt: Long = 0L,
    val manuallyConfirmedStage: ExpressionStage? = null,
    val lastRelationshipEventAt: Long? = null,
    val updatedAt: Long = 0L,
)

data class RelationshipStageEvidence(
    val validSessions30d: Int = 0,
    val approachEventCount14d: Int = 0,
    val distinctCareEventTypes30d: Int = 0,
    val hasAffectionEvent: Boolean = false,
    val hasDirectExpressionEvent: Boolean = false,
    val relationshipConfirmed: Boolean = false,
)

data class DimensionWeightState(
    val personId: String,
    val actor: ActorSide,
    val dimension: WeightDimension,
    val recentRaw: Double = 0.0,
    val baseRaw: Double = 0.0,
    val updatedAt: Long = 0L,
)
