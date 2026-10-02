package io.chatweight.android.capture

import io.chatweight.android.capture.ocr.OcrLine
import kotlin.math.abs

/** Select a centered toolbar label from the screenshot, above all chat bubbles. */
object WeChatTitleOcr {
    private val groupSuffix = Regex("[（(]\\d+[)）]$")
    private val sentencePunctuation = Regex("[，。？！、：:]")

    fun pick(lines: List<OcrLine>, screenWidth: Int, firstBubbleTop: Int): String? {
        val center = screenWidth / 2
        return lines.asSequence()
            .map { it.text.trim() to it.bounds }
            .filter { (value, bounds) ->
                value.length in 1..24 && bounds.bottom < firstBubbleTop &&
                    bounds.centerX() in (screenWidth / 5)..(screenWidth * 4 / 5) &&
                    !sentencePunctuation.containsMatchIn(value) &&
                    value !in setOf("微信", "返回", "聊天信息", "更多功能")
            }
            .sortedWith(compareByDescending<Pair<String, android.graphics.Rect>> { groupSuffix.containsMatchIn(it.first) }
                .thenBy { abs(it.second.centerX() - center) })
            .firstOrNull()?.first
    }
}
