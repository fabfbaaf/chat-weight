package io.chatweight.core

object WeightEngine {
    data class ApplyResult(val state: DimensionWeightState, val effectiveDelta: Double)

    fun apply(
        state: DimensionWeightState,
        event: DetectedWeightEvent,
        occurrence: Int = 1,
        positiveUsedToday: Double = 0.0,
        negativeUsedToday: Double = 0.0,
    ): ApplyResult {
        val rule = WeightRuleRegistry.rules[event.eventType] ?: return ApplyResult(state, 0.0)
        val repeat = if (rule.repeatable) DecayEngine.repeatMultiplier(occurrence) else 1.0
        var delta = rule.baseDelta * repeat * event.confidence.coerceIn(0.0, 1.0)
        val caps = dailyCaps(rule.dimension)
        delta = if (delta >= 0.0) {
            delta.coerceAtMost((caps.first - positiveUsedToday).coerceAtLeast(0.0))
        } else {
            val allowed = caps.second - negativeUsedToday
            delta.coerceAtLeast(allowed).coerceAtMost(0.0)
        }

        val elapsedDays = if (state.updatedAt == 0L) 0.0 else
            (event.eventTime - state.updatedAt).coerceAtLeast(0L).toDouble() / 86_400_000.0
        val recent = DecayEngine.decay(state.recentRaw, elapsedDays, DecayEngine.recentHalfLifeDays(rule.dimension))
        val base = DecayEngine.decay(state.baseRaw, elapsedDays, DecayEngine.BASE_HALF_LIFE_DAYS)
        return ApplyResult(
            state.copy(
                recentRaw = recent + delta,
                baseRaw = base + delta * rule.baseShare,
                updatedAt = event.eventTime,
            ),
            delta,
        )
    }

    private fun dailyCaps(dimension: WeightDimension): Pair<Double, Double> =
        if (dimension == WeightDimension.FREQUENCY) 3.0 to -2.0 else 8.0 to -4.0
}
