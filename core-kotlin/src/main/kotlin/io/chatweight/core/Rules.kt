package io.chatweight.core

data class WeightRule(
    val eventType: WeightEventType,
    val dimension: WeightDimension,
    val baseDelta: Double,
    val repeatable: Boolean = true,
    val repeatGroup: String? = null,
    val maxPerSession: Int? = null,
    val baseShare: Double = 0.25,
)

object WeightRuleRegistry {
    val rules: Map<WeightEventType, WeightRule> = listOf(
        WeightRule(WeightEventType.SESSION_START, WeightDimension.INITIATIVE, 3.0, repeatable = false),
        WeightRule(WeightEventType.FOLLOW_UP_WITHOUT_REPLY, WeightDimension.INITIATIVE, 0.8, repeatGroup = "follow_up"),
        WeightRule(WeightEventType.REPLY_WITHIN_1M, WeightDimension.RESPONSE, 1.2, repeatGroup = "reply_speed"),
        WeightRule(WeightEventType.REPLY_WITHIN_5M, WeightDimension.RESPONSE, 1.0, repeatGroup = "reply_speed"),
        WeightRule(WeightEventType.REPLY_WITHIN_15M, WeightDimension.RESPONSE, 0.7, repeatGroup = "reply_speed"),
        WeightRule(WeightEventType.REPLY_WITHIN_60M, WeightDimension.RESPONSE, 0.4, repeatGroup = "reply_speed"),
        WeightRule(WeightEventType.REPLY_WITHIN_6H, WeightDimension.RESPONSE, 0.1, repeatGroup = "reply_speed"),
        WeightRule(WeightEventType.QUESTION_UNANSWERED_24H, WeightDimension.RESPONSE, -0.5),
        WeightRule(WeightEventType.MULTIPLE_QUESTIONS_UNANSWERED, WeightDimension.RESPONSE, -0.8),
        WeightRule(WeightEventType.LONG_REPLY_1_5X, WeightDimension.EFFORT, 0.3, repeatGroup = "long_reply"),
        WeightRule(WeightEventType.LONG_REPLY_3X, WeightDimension.EFFORT, 0.7, repeatGroup = "long_reply"),
        WeightRule(WeightEventType.LONG_REPLY_6X, WeightDimension.EFFORT, 1.0, repeatGroup = "long_reply"),
        WeightRule(WeightEventType.BURST_2_3, WeightDimension.EFFORT, 0.2),
        WeightRule(WeightEventType.BURST_4_PLUS, WeightDimension.EFFORT, 0.4),
        WeightRule(WeightEventType.SHORT_REPLY_CHAIN_3, WeightDimension.EFFORT, -0.4, maxPerSession = 1),
        WeightRule(WeightEventType.SHORT_REPLY_CHAIN_5, WeightDimension.EFFORT, -0.5, maxPerSession = 1),
        WeightRule(WeightEventType.SESSION_4_TURNS, WeightDimension.CONTINUITY, 0.4, repeatable = false),
        WeightRule(WeightEventType.SESSION_8_TURNS, WeightDimension.CONTINUITY, 0.6, repeatable = false),
        WeightRule(WeightEventType.SESSION_15_TURNS, WeightDimension.CONTINUITY, 1.0, repeatable = false),
        WeightRule(WeightEventType.SESSION_30_TURNS, WeightDimension.CONTINUITY, 1.5, repeatable = false),
        WeightRule(WeightEventType.ACTIVE_DAY, WeightDimension.FREQUENCY, 0.6, repeatable = false),
        WeightRule(WeightEventType.ACTIVE_STREAK_3D, WeightDimension.FREQUENCY, 0.5, repeatable = false),
        WeightRule(WeightEventType.ACTIVE_STREAK_7D, WeightDimension.FREQUENCY, 1.0, repeatable = false),
        WeightRule(WeightEventType.ACTIVE_STREAK_14D, WeightDimension.FREQUENCY, 1.5, repeatable = false),
    ).associateBy { it.eventType }
}

data class RelationshipRule(
    val type: RelationshipEventType,
    val category: RelationshipEventCategory,
    val progressDelta: Double,
    val heatDelta: Double,
    val repeatGroup: String? = null,
    val maxPerSession: Int? = null,
    val maxPerDay: Int? = null,
    val requiresSelfActor: Boolean = true,
)

object RelationshipRuleRegistry {
    private fun rule(
        type: RelationshipEventType,
        category: RelationshipEventCategory,
        progress: Double,
        heat: Double,
        repeatGroup: String? = null,
        maxPerSession: Int? = null,
        maxPerDay: Int? = null,
        requiresSelfActor: Boolean = true,
    ) = RelationshipRule(type, category, progress, heat, repeatGroup, maxPerSession, maxPerDay, requiresSelfActor)

    val rules = listOf(
        rule(RelationshipEventType.PERSONAL_TOPIC, RelationshipEventCategory.FAMILIARITY, 0.3, 0.5, "personal_topic", maxPerDay = 3),
        rule(RelationshipEventType.PERSONAL_QUESTION, RelationshipEventCategory.FAMILIARITY, 0.5, 0.7, "personal_question", maxPerDay = 3),
        rule(RelationshipEventType.SELF_DISCLOSURE, RelationshipEventCategory.FAMILIARITY, 0.8, 1.0, "self_disclosure", maxPerDay = 3),
        rule(RelationshipEventType.SHARED_EXPERIENCE, RelationshipEventCategory.FAMILIARITY, 0.8, 1.0, maxPerDay = 2),
        rule(RelationshipEventType.INITIATE_PRIVATE_CHAT, RelationshipEventCategory.APPROACH, 1.0, 1.5, "approach", maxPerDay = 3),
        rule(RelationshipEventType.TARGETED_SHARING, RelationshipEventCategory.APPROACH, 1.0, 1.5, maxPerDay = 3),
        rule(RelationshipEventType.CONTINUE_CONVERSATION, RelationshipEventCategory.APPROACH, 0.5, 0.7, "continue", maxPerSession = 2),
        rule(RelationshipEventType.INITIATE_VOICE_CALL, RelationshipEventCategory.APPROACH, 1.2, 1.8, maxPerDay = 2),
        rule(RelationshipEventType.INITIATE_ACTIVITY, RelationshipEventCategory.APPROACH, 1.2, 1.8, maxPerDay = 2),
        rule(RelationshipEventType.INITIATE_MEETUP, RelationshipEventCategory.APPROACH, 2.0, 2.5, maxPerDay = 1),
        rule(RelationshipEventType.CHECK_IN, RelationshipEventCategory.CARE, 1.0, 1.5, maxPerDay = 3),
        rule(RelationshipEventType.REMEMBER_AND_FOLLOW_UP, RelationshipEventCategory.CARE, 1.5, 2.0, maxPerDay = 2),
        rule(RelationshipEventType.EMOTIONAL_SUPPORT, RelationshipEventCategory.CARE, 1.5, 2.0, maxPerDay = 3),
        rule(RelationshipEventType.PRACTICAL_SUPPORT, RelationshipEventCategory.CARE, 1.2, 1.5, maxPerDay = 3),
        rule(RelationshipEventType.SAFETY_CONCERN, RelationshipEventCategory.CARE, 0.8, 1.2, maxPerDay = 3),
        rule(RelationshipEventType.SPECIAL_DATE_ATTENTION, RelationshipEventCategory.CARE, 1.5, 2.0, maxPerDay = 1),
        rule(RelationshipEventType.SPECIAL_COMPLIMENT, RelationshipEventCategory.AFFECTION, 1.0, 1.5, maxPerDay = 2),
        rule(RelationshipEventType.SPECIAL_NICKNAME, RelationshipEventCategory.AFFECTION, 1.5, 1.5, maxPerDay = 2),
        rule(RelationshipEventType.LIGHT_FLIRT, RelationshipEventCategory.AFFECTION, 2.5, 3.0, maxPerDay = 2),
        rule(RelationshipEventType.LIGHT_MISSING_EXPRESSION, RelationshipEventCategory.AFFECTION, 3.0, 3.5, maxPerDay = 2),
        rule(RelationshipEventType.CARE_EXPRESSION, RelationshipEventCategory.AFFECTION, 2.0, 2.5, maxPerDay = 2),
        rule(RelationshipEventType.DEPENDENCY_EXPRESSION, RelationshipEventCategory.AFFECTION, 2.0, 2.5, maxPerDay = 2),
        rule(RelationshipEventType.SPECIAL_IMPORTANCE_EXPRESSION, RelationshipEventCategory.AFFECTION, 3.0, 3.5, maxPerDay = 2),
        rule(RelationshipEventType.DIRECT_LIKE_EXPRESSION, RelationshipEventCategory.DIRECT_EXPRESSION, 10.0, 8.0, maxPerDay = 1),
        rule(RelationshipEventType.DIRECT_ROMANTIC_INTENT, RelationshipEventCategory.DIRECT_EXPRESSION, 10.0, 8.0, maxPerDay = 1),
        rule(RelationshipEventType.PURSUIT_EXPRESSION, RelationshipEventCategory.DIRECT_EXPRESSION, 10.0, 8.0, maxPerDay = 1),
        rule(RelationshipEventType.MUTUAL_AFFECTION_EXPRESSION, RelationshipEventCategory.RELATIONSHIP, 5.0, 6.0, requiresSelfActor = false),
        rule(RelationshipEventType.POSSIBLE_RELATIONSHIP_CONFIRMED, RelationshipEventCategory.RELATIONSHIP, 0.0, 2.0, requiresSelfActor = false),
        rule(RelationshipEventType.RELATIONSHIP_CONFIRMED, RelationshipEventCategory.RELATIONSHIP, 0.0, 5.0, requiresSelfActor = false),
        rule(RelationshipEventType.FRIEND_ONLY_EXPRESSION, RelationshipEventCategory.RETREAT, -8.0, -6.0, maxPerDay = 1),
        rule(RelationshipEventType.WITHDRAW_AFFECTION, RelationshipEventCategory.RETREAT, -5.0, -5.0, maxPerDay = 1),
        rule(RelationshipEventType.STOP_PURSUIT, RelationshipEventCategory.RETREAT, -10.0, -10.0, maxPerDay = 1),
        rule(RelationshipEventType.RELATIONSHIP_ENDED, RelationshipEventCategory.RETREAT, 0.0, -15.0, maxPerDay = 1, requiresSelfActor = false),
    ).associateBy { it.type }
}
