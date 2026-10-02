package io.chatweight.android.reply

import io.chatweight.android.core.ChatSnapshot
import io.chatweight.android.ingest.LocalSummary
import org.json.JSONObject

/** Bounded context: at most ten visible lines plus one small derived relationship summary. */
object ReplyContextBuilder {
    fun recentSnapshot(snapshot: ChatSnapshot): ChatSnapshot = snapshot.copy(messages = snapshot.messages.takeLast(10))

    fun relationshipContext(summary: LocalSummary?, fallback: String): String {
        if (summary == null) return fallback.take(100)
        return JSONObject()
            .put("relationship_type", summary.relationshipType)
            .put("expression_stage", summary.expressionStage)
            .put("self_engagement", summary.selfEngagement.toInt())
            .put("other_engagement", summary.otherEngagement.toInt())
            .put("recent_heat", summary.recentHeat.toInt())
            .toString()
    }
}
