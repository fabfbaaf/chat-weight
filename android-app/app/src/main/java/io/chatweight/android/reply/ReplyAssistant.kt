package io.chatweight.android.reply

import io.chatweight.android.core.Analysis
import io.chatweight.android.core.ChatSnapshot
import io.chatweight.android.core.Prefs
import io.chatweight.android.core.RankedReply
import io.chatweight.android.ingest.LocalSummary
import io.chatweight.android.jev.JudgeClient
import io.chatweight.android.jev.ReplyClient

data class ReplyOutcome(val judgment: Analysis?, val candidates: List<RankedReply>, val reason: String? = null)

/** Optional network branch. Call only after the local Room transaction commits. */
class ReplyAssistant(private val prefs: Prefs) {
    fun analyze(snapshot: ChatSnapshot, summary: LocalSummary?, manual: Boolean = false): ReplyOutcome {
        if (!prefs.aiReplyEnabled) return ReplyOutcome(null, emptyList(), "AI 回复已关闭")
        if (!prefs.hasKey()) return ReplyOutcome(null, emptyList(), "未配置判断接口密钥")
        val bounded = ReplyContextBuilder.recentSnapshot(snapshot)
        val relationship = ReplyContextBuilder.relationshipContext(summary, prefs.relationship)
        val judge = JudgeClient(prefs)
        val compatible = if (prefs.judgeProvider == Prefs.PROVIDER_CUSTOM &&
            prefs.judgeEndpoint().trimEnd('/').endsWith("/chat/completions")) CompatibleJudgeClient(prefs) else null
        val judgment = compatible?.judge(bounded, relationship) ?: judge.judge(bounded, relationship)
        if (judgment.error != null) return ReplyOutcome(judgment, emptyList(), "判断接口暂不可用")
        if (!manual && (judgment.shouldReplyNow ?: 1.0) < 0.25)
            return ReplyOutcome(judgment, emptyList(), "当前无需立即回复")
        return try {
            val drafts = ReplyClient(prefs).draft(bounded, relationship, judgment = judgment)
            val ranked = try {
                compatible?.rank(bounded, drafts) ?: judge.rank(bounded, relationship, drafts)
            } catch (_: Exception) {
                drafts.map { RankedReply(it, 1.0 / drafts.size.coerceAtLeast(1)) }
            }
            ReplyOutcome(judgment, ranked.take(3))
        } catch (_: Exception) {
            ReplyOutcome(judgment, emptyList(), "回复接口暂不可用")
        }
    }
}
