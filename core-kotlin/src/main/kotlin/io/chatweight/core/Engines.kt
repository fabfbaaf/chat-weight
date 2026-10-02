package io.chatweight.core

import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.pow

object DecayEngine {
    private val recentHalfLife = mapOf(
        WeightDimension.INITIATIVE to 30.0,
        WeightDimension.RESPONSE to 14.0,
        WeightDimension.EFFORT to 30.0,
        WeightDimension.CONTINUITY to 30.0,
        WeightDimension.FREQUENCY to 14.0,
    )

    fun recentHalfLifeDays(dimension: WeightDimension): Double = recentHalfLife.getValue(dimension)
    const val BASE_HALF_LIFE_DAYS = 180.0
    const val SCORE_K = 20.0

    fun decay(value: Double, elapsedDays: Double, halfLifeDays: Double): Double =
        if (elapsedDays <= 0.0) value else value * 2.0.pow(-elapsedDays / halfLifeDays)

    fun rawToScore(raw: Double, k: Double = SCORE_K): Double = 100.0 * (1.0 - exp(-raw.coerceAtLeast(0.0) / k))

    fun repeatMultiplier(occurrence: Int): Double = when (occurrence) {
        1 -> 1.0
        2 -> 0.7
        3 -> 0.5
        else -> 0.3
    }

    fun mutuality(self: Double, other: Double): Double {
        val balance = 1.0 - abs(self - other) / (self + other + 1.0)
        return ((self + other) / 2.0) * balance
    }
}

object RelationshipHeatEngine {
    const val HALF_LIFE_DAYS = 14.0
    const val SCORE_K = 12.0

    fun decay(raw: Double, from: Long, to: Long): Double {
        if (to <= from) return raw
        val days = (to - from).toDouble() / 86_400_000.0
        return DecayEngine.decay(raw, days, HALF_LIFE_DAYS)
    }

    fun toScore(raw: Double): Double = DecayEngine.rawToScore(raw, SCORE_K)
}

object RelationshipStageEvaluator {
    fun evaluate(profile: RelationshipProfileState, evidence: RelationshipStageEvidence): ExpressionStage {
        profile.manuallyConfirmedStage?.let { return it }
        if (evidence.relationshipConfirmed) return ExpressionStage.RELATIONSHIP_CONFIRMED
        if (evidence.hasDirectExpressionEvent) return ExpressionStage.DIRECT_EXPRESSION
        val raw = profile.expressionRaw
        if (raw >= 60.0 && evidence.hasAffectionEvent) return ExpressionStage.LIGHT_AFFECTION
        if (raw >= 45.0 && evidence.distinctCareEventTypes30d >= 2) return ExpressionStage.OBVIOUS_CARE
        if (raw >= 30.0 && evidence.approachEventCount14d >= 3) return ExpressionStage.APPROACHING
        if (raw >= 15.0 && evidence.validSessions30d >= 3) return ExpressionStage.FAMILIARITY
        return ExpressionStage.NORMAL_CONTACT
    }
}

object RelationshipEngine {
    fun apply(
        profile: RelationshipProfileState,
        event: RelationshipEventCandidate,
        evidence: RelationshipStageEvidence,
        repeatMultiplier: Double = 1.0,
    ): RelationshipProfileState {
        val rule = RelationshipRuleRegistry.rules[event.eventType] ?: return profile
        if (rule.requiresSelfActor && event.actorSide != ActorSide.SELF) return profile

        val confidence = event.confidence.coerceIn(0.0, 1.0)
        val progressDelta = rule.progressDelta * repeatMultiplier * confidence
        val heatDelta = rule.heatDelta * repeatMultiplier * confidence
        val heatFrom = if (profile.heatUpdatedAt == 0L) event.eventTime else profile.heatUpdatedAt
        val decayedHeat = RelationshipHeatEngine.decay(profile.expressionHeatRaw, heatFrom, event.eventTime)

        var updated = profile.copy(
            expressionRaw = (profile.expressionRaw + progressDelta).coerceIn(0.0, 100.0),
            expressionHeatRaw = (decayedHeat + heatDelta).coerceAtLeast(0.0),
            heatUpdatedAt = event.eventTime,
            lastRelationshipEventAt = event.eventTime,
            updatedAt = event.eventTime,
        )

        updated = if (rule.category == RelationshipEventCategory.RETREAT) {
            updated.copy(expressionStage = retreatStage(updated.expressionStage, event.eventType))
        } else {
            val evaluated = RelationshipStageEvaluator.evaluate(updated, evidence)
            updated.copy(expressionStage = maxStage(updated.expressionStage, evaluated))
        }
        return updated.copy(highestExpressionStage = maxStage(updated.highestExpressionStage, updated.expressionStage))
    }

    private fun retreatStage(current: ExpressionStage, type: RelationshipEventType): ExpressionStage = when (type) {
        RelationshipEventType.FRIEND_ONLY_EXPRESSION -> ExpressionStage.FAMILIARITY
        RelationshipEventType.WITHDRAW_AFFECTION -> minStage(current, ExpressionStage.OBVIOUS_CARE)
        RelationshipEventType.STOP_PURSUIT -> ExpressionStage.FAMILIARITY
        RelationshipEventType.RELATIONSHIP_ENDED -> ExpressionStage.NORMAL_CONTACT
        else -> current
    }

    private fun maxStage(a: ExpressionStage, b: ExpressionStage) = if (a.level >= b.level) a else b
    private fun minStage(a: ExpressionStage, b: ExpressionStage) = if (a.level <= b.level) a else b
}
