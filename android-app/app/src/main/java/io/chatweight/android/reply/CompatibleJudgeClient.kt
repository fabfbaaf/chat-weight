package io.chatweight.android.reply

import io.chatweight.android.core.Analysis
import io.chatweight.android.core.ChatSnapshot
import io.chatweight.android.core.Choice
import io.chatweight.android.core.Prefs
import io.chatweight.android.core.RankedReply
import io.chatweight.android.jev.HttpJson
import io.chatweight.android.jev.Route
import org.json.JSONArray
import org.json.JSONObject

/** Judge and rank over a user-configured OpenAI-compatible chat endpoint. */
class CompatibleJudgeClient(private val prefs: Prefs) {
    fun judge(snapshot: ChatSnapshot, relationship: String): Analysis {
        val start = System.currentTimeMillis()
        return try {
            val conversation = snapshot.messages.takeLast(10).joinToString("\n") {
                "${if (it.side == "me") "我" else "对方"}：${it.text}"
            }
            val answer = ask("只返回 JSON 对象，字段 intent 为对方消息的简短意图，字段 should_reply_now 为 0 到 1 的数字。不要猜测未写出的事实。",
                "关系摘要：${relationship.take(300)}\n最近对话：\n$conversation")
            val json = parseObject(answer)
            Analysis(
                trueIntent = json.optString("intent").takeIf { it.isNotBlank() }
                    ?.let { Choice(it.take(60), 0.7, emptyMap()) },
                dangerLevel = null, sheNeeds = null,
                shouldReplyNow = json.optDouble("should_reply_now", 1.0).coerceIn(0.0, 1.0),
                bestAction = null, tensionResolved = null, literalQuestion = null,
                rankedReplies = emptyList(), latencyMs = System.currentTimeMillis() - start,
            )
        } catch (_: Exception) {
            Analysis(null, null, null, null, null, null, null, emptyList(),
                System.currentTimeMillis() - start, error = "判断接口暂不可用")
        }
    }

    fun rank(snapshot: ChatSnapshot, drafts: List<String>): List<RankedReply> {
        val recent = snapshot.messages.lastOrNull()?.text.orEmpty().take(500)
        val answer = ask("只返回 JSON 数组，按适合当前对话的顺序排列候选编号，例如 [2,1,3]。", "最近消息：$recent\n" +
            drafts.take(3).mapIndexed { index, value -> "${index + 1}. ${value.take(80)}" }.joinToString("\n"))
        val start = answer.indexOf('['); val end = answer.lastIndexOf(']')
        val order = if (start >= 0 && end > start) runCatching {
            JSONArray(answer.substring(start, end + 1)).let { array ->
                (0 until array.length()).map { array.getInt(it) - 1 }.filter { it in drafts.indices }.distinct()
            }
        }.getOrDefault(emptyList()) else emptyList()
        val indices = (order + drafts.indices).distinct()
        return indices.take(3).mapIndexed { rank, index -> RankedReply(drafts[index], (3 - rank) / 3.0) }
    }

    private fun ask(system: String, user: String): String {
        val body = JSONObject().put("model", prefs.judgeModel).put("messages", JSONArray()
            .put(JSONObject().put("role", "system").put("content", system))
            .put(JSONObject().put("role", "user").put("content", user)))
        val response = HttpJson.post(prefs.judgeEndpoint(), prefs.judgeKey, body, Route.JUDGE,
            HttpJson.headersFor(prefs.judgeEndpoint()))
        return response.optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("message")?.optString("content").orEmpty()
    }

    private fun parseObject(answer: String): JSONObject {
        val start = answer.indexOf('{'); val end = answer.lastIndexOf('}')
        require(start >= 0 && end > start)
        return JSONObject(answer.substring(start, end + 1))
    }
}
