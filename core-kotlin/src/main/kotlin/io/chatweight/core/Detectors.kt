package io.chatweight.core

import java.util.UUID

private const val SESSION_GAP_MS = 30L * 60L * 1000L

data class RelationshipDetectionContext(
    val currentMessage: UnifiedMessage,
    val previousMessages: List<UnifiedMessage> = emptyList(),
    val session: ChatSession? = null,
    val specialNicknames: Set<String> = emptySet(),
)

interface RelationshipDetector {
    fun detect(context: RelationshipDetectionContext): List<RelationshipEventCandidate>
}

private fun candidate(
    ctx: RelationshipDetectionContext,
    type: RelationshipEventType,
    source: DetectionSource,
    confidence: Double,
    policy: ConfirmationPolicy,
    reason: String,
): RelationshipEventCandidate = RelationshipEventCandidate(
    id = UUID.randomUUID().toString(),
    personId = ctx.currentMessage.personId ?: "unknown",
    conversationId = ctx.currentMessage.conversationId,
    actorSide = ctx.currentMessage.actorSide,
    eventType = type,
    source = source,
    confidence = confidence,
    confirmationPolicy = policy,
    status = if (policy == ConfirmationPolicy.AUTO_APPLY) CandidateStatus.AUTO_CONFIRMED else CandidateStatus.PENDING,
    eventTime = ctx.currentMessage.messageTime,
    sessionId = ctx.session?.id,
    sourceMessageIds = listOf(ctx.currentMessage.id),
    evidenceText = ctx.currentMessage.text,
    reasonCode = reason,
)

class LocalBehaviorDetector : RelationshipDetector {
    override fun detect(context: RelationshipDetectionContext): List<RelationshipEventCandidate> {
        val cur = context.currentMessage
        if (cur.direction == MessageDirection.SYSTEM) return emptyList()
        val out = mutableListOf<RelationshipEventCandidate>()
        val prev = context.previousMessages.lastOrNull()
        val sessionStart = prev == null || cur.messageTime - prev.messageTime >= SESSION_GAP_MS
        if (sessionStart) {
            out += candidate(context, RelationshipEventType.INITIATE_PRIVATE_CHAT, DetectionSource.LOCAL_FACT, 1.0,
                ConfirmationPolicy.AUTO_APPLY, "session_start_by_actor")
        }
        if (cur.type in setOf(MessageType.IMAGE, MessageType.VIDEO, MessageType.LINK)) {
            val requested = prev?.text?.let { Regex("(发(我|一下)|给我|看看|链接|照片|图片|视频)").containsMatchIn(it) } ?: false
            if (!requested) {
                out += candidate(context, RelationshipEventType.TARGETED_SHARING, DetectionSource.LOCAL_FACT, 0.82,
                    ConfirmationPolicy.HIGH_CONFIDENCE_ONLY, "unsolicited_media_or_link_share")
            }
        }
        return out
    }
}

class LocalPhraseDetector : RelationshipDetector {
    private val checkIn = Regex("(你.*(怎么样|还好吗|好点了吗|累不累|到家了吗|吃了吗|睡了吗)|到家了没|还难受吗)")
    private val missing = Regex("((有点|突然|挺|很|好)?想(你|你了)|想念你|老想到你)")
    private val directLike = Regex("(我(真的|其实|挺|很)?喜欢你|我对你.*(有感觉|不是普通朋友)|我想追你)")
    private val friendOnly = Regex("(只把你当朋友|我们还是做朋友吧|就做朋友吧)")
    private val relationConfirmed = Regex("(我们在一起吧|那我们算.*(情侣|在一起)|你就是我(女朋友|男朋友))")
    private val relationEnded = Regex("(分手吧|我们分手|以后别联系了|到这里吧)")
    private val negMissing = listOf("不想你", "没想你", "才不想", "谁想你")

    override fun detect(context: RelationshipDetectionContext): List<RelationshipEventCandidate> {
        val text = context.currentMessage.text?.trim().orEmpty()
        if (text.isEmpty()) return emptyList()
        val out = mutableListOf<RelationshipEventCandidate>()
        if (checkIn.containsMatchIn(text)) out += candidate(context, RelationshipEventType.CHECK_IN,
            DetectionSource.LOCAL_SEMANTIC_RULE, 0.86, ConfirmationPolicy.HIGH_CONFIDENCE_ONLY, "check_in_phrase")
        if (missing.containsMatchIn(text) && negMissing.none { it in text }) out += candidate(context,
            RelationshipEventType.LIGHT_MISSING_EXPRESSION, DetectionSource.LOCAL_SEMANTIC_RULE, 0.91,
            ConfirmationPolicy.HIGH_CONFIDENCE_ONLY, "explicit_missing_phrase")
        if (context.specialNicknames.any { it.isNotEmpty() && it in text }) out += candidate(context,
            RelationshipEventType.SPECIAL_NICKNAME, DetectionSource.LOCAL_SEMANTIC_RULE, 0.98,
            ConfirmationPolicy.AUTO_APPLY, "configured_special_nickname")
        if (directLike.containsMatchIn(text)) {
            val type = if ("追你" in text) RelationshipEventType.PURSUIT_EXPRESSION else RelationshipEventType.DIRECT_LIKE_EXPRESSION
            out += candidate(context, type, DetectionSource.LOCAL_SEMANTIC_RULE, 0.98,
                ConfirmationPolicy.USER_REVIEW, "explicit_romantic_phrase")
        }
        if (friendOnly.containsMatchIn(text)) out += candidate(context, RelationshipEventType.FRIEND_ONLY_EXPRESSION,
            DetectionSource.LOCAL_SEMANTIC_RULE, 0.96, ConfirmationPolicy.USER_REVIEW, "friend_only_phrase")
        if (relationConfirmed.containsMatchIn(text)) out += candidate(context, RelationshipEventType.POSSIBLE_RELATIONSHIP_CONFIRMED,
            DetectionSource.LOCAL_SEMANTIC_RULE, 0.90, ConfirmationPolicy.MANUAL_ONLY, "relationship_confirmation_phrase")
        if (relationEnded.containsMatchIn(text)) out += candidate(context, RelationshipEventType.RELATIONSHIP_ENDED,
            DetectionSource.LOCAL_SEMANTIC_RULE, 0.90, ConfirmationPolicy.MANUAL_ONLY, "relationship_end_phrase")
        return out
    }
}

class RelationshipEventDetector(
    private val detectors: List<RelationshipDetector> = listOf(LocalBehaviorDetector(), LocalPhraseDetector()),
) {
    fun detect(context: RelationshipDetectionContext): List<RelationshipEventCandidate> =
        mergeAndDedupe(detectors.flatMap { it.detect(context) })

    internal fun mergeAndDedupe(items: List<RelationshipEventCandidate>): List<RelationshipEventCandidate> {
        val best = items.groupBy { it.eventType }.mapValues { (_, v) -> v.maxBy { it.confidence } }.toMutableMap()
        val suppresses = mapOf(
            RelationshipEventType.LIGHT_MISSING_EXPRESSION to setOf(RelationshipEventType.SELF_DISCLOSURE),
            RelationshipEventType.DIRECT_LIKE_EXPRESSION to setOf(RelationshipEventType.LIGHT_FLIRT, RelationshipEventType.SPECIAL_IMPORTANCE_EXPRESSION),
            RelationshipEventType.PURSUIT_EXPRESSION to setOf(RelationshipEventType.LIGHT_FLIRT),
            RelationshipEventType.REMEMBER_AND_FOLLOW_UP to setOf(RelationshipEventType.CHECK_IN),
        )
        suppresses.forEach { (high, lows) -> if (high in best) lows.forEach { best.remove(it) } }
        return best.values.sortedBy { it.eventType.name }
    }
}
