package io.chatweight.android.pipeline

import io.chatweight.android.database.ChatWeightRoom
import io.chatweight.android.database.entity.*
import io.chatweight.core.*
import org.json.JSONArray
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID
import kotlin.math.min

/** Runs only inside the caller's Room transaction on a background executor. */
class ChatWeightPipeline(private val db: ChatWeightRoom) {
    private val relationshipDetector = RelationshipEventDetector()

    fun process(message: UnifiedMessage) {
        if (db.algorithmMeta().insert(AlgorithmMetaEntity("processed:${message.id}", "1")) == -1L) return
        val personId = message.personId ?: return
        val previous = db.messages().previous(message.conversationId, message.id)?.toCore()
        val storedSession = db.sessions().latest(message.conversationId)
            ?.takeIf { message.messageTime - it.lastMessageAt < SessionManager.GAP_MS }
        val transition = SessionManager.ingest(message, storedSession?.toCore(previous?.actorSide))
        db.sessions().upsert(transition.session.toEntity())

        val recent = db.messages().recent(message.conversationId, 9)
            .filter { it.id != message.id }.asReversed().map { it.toCore() }
        val median = recent.mapNotNull { it.text?.length?.toDouble() }.sorted()
            .let { if (it.isEmpty()) 12.0 else it[it.size / 2] }
        WeightEventDetector.detect(message, previous, transition.session, transition.isNew, recent, median)
            .forEach { applyWeight(it) }
        applyActiveDay(message, transition.session)

        val ctx = RelationshipDetectionContext(message, recent, transition.session)
        relationshipDetector.detect(ctx).forEach { recordCandidate(it) }
        updateDailyMetrics(message, transition.session, transition.isNew, previous)
        writeSnapshots(personId, message.messageTime)
    }

    private fun applyActiveDay(message: UnifiedMessage, session: ChatSession) {
        val personId = message.personId ?: return
        val date = localDate(message.messageTime)
        val key = "active:$personId:${message.actorSide}:$date"
        applyWeight(DetectedWeightEvent(
            id = UUID.nameUUIDFromBytes(key.toByteArray(Charsets.UTF_8)).toString(),
            personId = personId, conversationId = message.conversationId,
            actor = message.actorSide, eventType = WeightEventType.ACTIVE_DAY,
            eventTime = message.messageTime, sessionId = session.id,
            sourceMessageIds = listOf(message.id),
        ))
    }

    private fun applyWeight(event: DetectedWeightEvent) {
        val rule = WeightRuleRegistry.rules[event.eventType] ?: return
        val sessionId = event.sessionId
        if (sessionId != null) {
            val count = db.weightEvents().countInSession(
                sessionId, event.personId, event.actor.name.lowercase(), event.eventType.name.lowercase()
            )
            if (!rule.repeatable && count > 0) return
            rule.maxPerSession?.let { if (count >= it) return }
        }
        val repeatGroup = rule.repeatGroup
        val occurrence = if (sessionId != null && repeatGroup != null)
            db.weightEvents().countRepeat(sessionId, event.personId, event.actor.name.lowercase(), repeatGroup).toInt() + 1
            else 1
        val (start, end) = dayBounds(event.eventTime)
        val actor = event.actor.name.lowercase()
        val dim = rule.dimension.name.lowercase()
        val positive = db.weightEvents().positiveUsed(event.personId, actor, dim, start, end)
        val negative = db.weightEvents().negativeUsed(event.personId, actor, dim, start, end)
        val old = db.weightStates().get(event.personId, actor, dim)?.let {
            DimensionWeightState(event.personId, event.actor, rule.dimension, it.recentRaw, it.baseRaw, it.updatedAt)
        } ?: DimensionWeightState(event.personId, event.actor, rule.dimension)
        val result = WeightEngine.apply(old, event, occurrence, positive, negative)
        if (result.effectiveDelta == 0.0) return
        val inserted = db.weightEvents().insert(WeightEventEntity(
            id = event.id, personId = event.personId, conversationId = event.conversationId,
            sessionId = event.sessionId, actorSide = actor, eventType = event.eventType.name.lowercase(),
            dimension = dim, baseDelta = rule.baseDelta,
            repeatMultiplier = if (rule.repeatable) DecayEngine.repeatMultiplier(occurrence) else 1.0,
            confidenceMultiplier = event.confidence, capMultiplier = 1.0,
            effectiveDelta = result.effectiveDelta, eventTime = event.eventTime,
            repeatGroup = rule.repeatGroup,
            sourceMessageIdsJson = JSONArray(event.sourceMessageIds).toString(),
            createdAt = event.eventTime,
        ))
        if (inserted == -1L) return
        db.weightStates().upsert(WeightStateEntity(
            personId = event.personId, actorSide = actor, dimension = dim,
            recentRaw = result.state.recentRaw, baseRaw = result.state.baseRaw,
            updatedAt = result.state.updatedAt,
        ))
    }

    private fun recordCandidate(candidate: RelationshipEventCandidate) {
        if (candidate.personId == "unknown") return
        val key = "${candidate.sourceMessageIds.firstOrNull()}:${candidate.eventType.name}"
        val id = UUID.nameUUIDFromBytes(key.toByteArray(Charsets.UTF_8)).toString()
        val inserted = db.relationshipCandidates().insert(RelationshipEventCandidateEntity(
            id = id, personId = candidate.personId, conversationId = candidate.conversationId,
            sessionId = candidate.sessionId, actorSide = candidate.actorSide.name.lowercase(),
            eventType = candidate.eventType.name.lowercase(), source = candidate.source.name.lowercase(),
            confidence = candidate.confidence, confirmationPolicy = candidate.confirmationPolicy.name.lowercase(),
            status = "pending", eventTime = candidate.eventTime,
            sourceMessageIdsJson = JSONArray(candidate.sourceMessageIds).toString(),
            evidenceText = candidate.evidenceText, reasonCode = candidate.reasonCode,
            dedupeKey = key, createdAt = candidate.eventTime,
        ))
        if (inserted == -1L) return
        if (candidate.confirmationPolicy == ConfirmationPolicy.AUTO_APPLY ||
            candidate.confirmationPolicy == ConfirmationPolicy.HIGH_CONFIDENCE_ONLY && candidate.confidence >= 0.80
        ) confirmCandidate(id, automatic = true)
    }

    fun confirmCandidate(id: String, automatic: Boolean = false): Boolean {
        val item = db.relationshipCandidates().get(id) ?: return false
        if (item.status != "pending") return item.status in setOf("confirmed", "auto_confirmed")
        val policy = ConfirmationPolicy.valueOf(item.confirmationPolicy.uppercase())
        if (automatic && policy in setOf(ConfirmationPolicy.USER_REVIEW, ConfirmationPolicy.MANUAL_ONLY)) return false
        val type = RelationshipEventType.valueOf(item.eventType.uppercase())
        val rule = RelationshipRuleRegistry.rules[type] ?: return false
        val core = RelationshipEventCandidate(
            id = id, personId = item.personId, conversationId = item.conversationId,
            actorSide = ActorSide.valueOf(item.actorSide.uppercase()), eventType = type,
            source = DetectionSource.valueOf(item.source.uppercase()), confidence = item.confidence,
            confirmationPolicy = policy, status = CandidateStatus.CONFIRMED,
            eventTime = item.eventTime, sessionId = item.sessionId,
            sourceMessageIds = jsonStrings(item.sourceMessageIdsJson),
            evidenceText = item.evidenceText, reasonCode = item.reasonCode.orEmpty(),
        )
        val (start, end) = dayBounds(item.eventTime)
        val maxPerDay = rule.maxPerDay
        if (maxPerDay != null && db.relationshipEvents().countInDay(item.personId, item.eventType, start, end) >= maxPerDay) {
            db.relationshipCandidates().changePending(id, if (automatic) "auto_confirmed" else "confirmed", System.currentTimeMillis())
            return true
        }
        val maxPerSession = rule.maxPerSession
        if (maxPerSession != null && item.sessionId != null &&
            db.relationshipEvents().countInSession(item.personId, item.sessionId, item.eventType) >= maxPerSession
        ) {
            db.relationshipCandidates().changePending(id, if (automatic) "auto_confirmed" else "confirmed", System.currentTimeMillis())
            return true
        }
        val profileEntity = db.relationshipProfiles().get(item.personId)
        val profile = profileEntity?.toCore() ?: RelationshipProfileState(item.personId)
        val evidence = evidence(item.personId, item.eventTime, core)
        val applied = if (profile.type in setOf(RelationshipType.CRUSH, RelationshipType.PARTNER))
            RelationshipEngine.apply(profile, core, evidence) else profile
        val inserted = db.relationshipEvents().insert(RelationshipEventEntity(
            id = id, personId = item.personId, conversationId = item.conversationId,
            sessionId = item.sessionId, actorSide = item.actorSide, eventType = item.eventType,
            eventCategory = rule.category.name.lowercase(), source = item.source,
            baseProgressDelta = rule.progressDelta, baseHeatDelta = rule.heatDelta,
            repeatMultiplier = 1.0, confidence = item.confidence,
            effectiveProgressDelta = if (applied === profile) 0.0 else rule.progressDelta * item.confidence,
            effectiveHeatDelta = if (applied === profile) 0.0 else rule.heatDelta * item.confidence,
            eventTime = item.eventTime, sourceMessageIdsJson = item.sourceMessageIdsJson,
            dedupeKey = item.dedupeKey, engineVersion = 1L, createdAt = System.currentTimeMillis(),
        ))
        if (inserted != -1L && applied !== profile) {
            db.relationshipProfiles().upsert(applied.toEntity(profileEntity?.createdAt ?: item.eventTime))
            writeSnapshots(item.personId, item.eventTime)
        }
        db.relationshipCandidates().changePending(id, if (automatic) "auto_confirmed" else "confirmed", System.currentTimeMillis())
        return true
    }

    fun rejectCandidate(id: String): Boolean =
        db.relationshipCandidates().changePending(id, "rejected", System.currentTimeMillis()) > 0

    fun setRelationshipType(personId: String, type: RelationshipType) {
        val now = System.currentTimeMillis()
        val existing = db.relationshipProfiles().get(personId)
        val profile = existing?.toCore() ?: RelationshipProfileState(personId)
        db.relationshipProfiles().upsert(profile.copy(type = type, updatedAt = now).toEntity(existing?.createdAt ?: now))
        writeSnapshots(personId, now)
    }

    private fun evidence(personId: String, now: Long, candidate: RelationshipEventCandidate): RelationshipStageEvidence {
        val events = db.relationshipEvents().since(personId, now - 30L * 86_400_000L)
        val types = events.mapNotNull { runCatching { RelationshipEventType.valueOf(it.eventType.uppercase()) }.getOrNull() } + candidate.eventType
        fun category(type: RelationshipEventType) = RelationshipRuleRegistry.rules[type]?.category
        return RelationshipStageEvidence(
            validSessions30d = db.sessions().validCountSince(personId, now - 30L * 86_400_000L).toInt(),
            approachEventCount14d = events.count { it.eventTime >= now - 14L * 86_400_000L && it.eventCategory == "approach" } +
                if (category(candidate.eventType) == RelationshipEventCategory.APPROACH) 1 else 0,
            distinctCareEventTypes30d = types.filter { category(it) == RelationshipEventCategory.CARE }.distinct().size,
            hasAffectionEvent = types.any { category(it) == RelationshipEventCategory.AFFECTION },
            hasDirectExpressionEvent = types.any { category(it) == RelationshipEventCategory.DIRECT_EXPRESSION },
            relationshipConfirmed = types.any { it == RelationshipEventType.RELATIONSHIP_CONFIRMED } ||
                candidate.eventType == RelationshipEventType.POSSIBLE_RELATIONSHIP_CONFIRMED,
        )
    }

    private fun updateDailyMetrics(message: UnifiedMessage, session: ChatSession, isNew: Boolean, previous: UnifiedMessage?) {
        val personId = message.personId ?: return
        val date = localDate(message.messageTime)
        val old = db.dailyMetrics().get(personId, date) ?: DailyMetricsEntity(personId = personId, localDate = date)
        db.dailyMetrics().upsert(old.copy(
            incomingMessages = old.incomingMessages + if (message.direction == MessageDirection.INCOMING) 1 else 0,
            outgoingMessages = old.outgoingMessages + if (message.direction == MessageDirection.OUTGOING) 1 else 0,
            incomingChars = old.incomingChars + if (message.direction == MessageDirection.INCOMING) (message.text?.length ?: 0) else 0,
            outgoingChars = old.outgoingChars + if (message.direction == MessageDirection.OUTGOING) (message.text?.length ?: 0) else 0,
            sessionCount = old.sessionCount + if (isNew) 1 else 0,
            selfStartedSessions = old.selfStartedSessions + if (isNew && message.actorSide == ActorSide.SELF) 1 else 0,
            otherStartedSessions = old.otherStartedSessions + if (isNew && message.actorSide == ActorSide.OTHER) 1 else 0,
            totalTurns = old.totalTurns + if (previous != null && previous.actorSide != message.actorSide) 1 else 0,
            activeMinutes = old.activeMinutes + if (previous != null && !isNew) min(30L, (message.messageTime - previous.messageTime).coerceAtLeast(0L) / 60_000L) else 0,
        ))
    }

    private fun writeSnapshots(personId: String, now: Long) {
        val date = localDate(now)
        val weights = mapOf(
            WeightDimension.INITIATIVE to 0.25, WeightDimension.RESPONSE to 0.25,
            WeightDimension.EFFORT to 0.20, WeightDimension.CONTINUITY to 0.20,
            WeightDimension.FREQUENCY to 0.10,
        )
        for (actor in listOf(ActorSide.SELF, ActorSide.OTHER)) {
            val scores = mutableMapOf<WeightDimension, Double>()
            var recentTotal = 0.0; var baseTotal = 0.0
            for (dim in WeightDimension.entries) {
                val state = db.weightStates().get(personId, actor.name.lowercase(), dim.name.lowercase())
                val elapsed = if (state == null) 0.0 else (now - state.updatedAt).coerceAtLeast(0L) / 86_400_000.0
                val recent = DecayEngine.decay(state?.recentRaw ?: 0.0, elapsed, DecayEngine.recentHalfLifeDays(dim))
                val base = DecayEngine.decay(state?.baseRaw ?: 0.0, elapsed, DecayEngine.BASE_HALF_LIFE_DAYS)
                scores[dim] = DecayEngine.rawToScore(recent * 0.75 + base * 0.25)
                recentTotal += recent; baseTotal += base
            }
            db.snapshots().upsertWeight(DailyWeightSnapshotEntity(
                personId = personId, localDate = date, actorSide = actor.name.lowercase(),
                initiativeScore = scores.getValue(WeightDimension.INITIATIVE),
                responseScore = scores.getValue(WeightDimension.RESPONSE),
                effortScore = scores.getValue(WeightDimension.EFFORT),
                continuityScore = scores.getValue(WeightDimension.CONTINUITY),
                frequencyScore = scores.getValue(WeightDimension.FREQUENCY),
                overallScore = weights.entries.sumOf { scores.getValue(it.key) * it.value },
                recentRawTotal = recentTotal, baseRawTotal = baseTotal,
                confidenceScore = min(100.0, db.sessions().validCountSince(personId, now - 30L * 86_400_000L) * 5.0),
                calculatedAt = now,
            ))
        }
        val profile = db.relationshipProfiles().get(personId) ?: RelationshipProfileState(personId).toEntity(now).also {
            db.relationshipProfiles().upsert(it)
        }
        val (start, _) = dayBounds(now)
        val events = db.relationshipEvents().since(personId, start)
        fun count(category: String) = events.count { it.eventCategory == category }.toLong()
        val heat = RelationshipHeatEngine.decay(profile.expressionHeatRaw, profile.heatUpdatedAt, now)
        db.snapshots().upsertRelationship(RelationshipDailySnapshotEntity(
            personId = personId, localDate = date, relationshipType = profile.relationshipType,
            expressionStage = profile.expressionStage, highestExpressionStage = profile.highestExpressionStage,
            expressionRaw = profile.expressionRaw, expressionProgressScore = profile.expressionRaw,
            expressionHeatRaw = heat, expressionHeatScore = RelationshipHeatEngine.toScore(heat),
            familiarityEventCount = count("familiarity"), approachEventCount = count("approach"),
            careEventCount = count("care"), affectionEventCount = count("affection"),
            directExpressionCount = count("direct_expression"), retreatEventCount = count("retreat"),
            validSessionCount = db.sessions().validCountSince(personId, start),
            calculatedAt = now, engineVersion = 1L,
        ))
    }

    private fun jsonStrings(value: String?): List<String> {
        if (value == null) return emptyList()
        return runCatching { JSONArray(value).let { array -> (0 until array.length()).map { array.getString(it) } } }
            .getOrDefault(emptyList())
    }

    private fun localDate(ms: Long): String = Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalDate().toString()
    private fun dayBounds(ms: Long): Pair<Long, Long> {
        val date = LocalDate.parse(localDate(ms))
        val zone = ZoneId.systemDefault()
        return date.atStartOfDay(zone).toInstant().toEpochMilli() to date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
    }
}
