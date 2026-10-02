package io.chatweight.android

import android.graphics.Rect
import io.chatweight.android.capture.OcrRefreshPolicy
import io.chatweight.android.capture.WeChatTitleOcr
import io.chatweight.android.capture.ocr.OcrLine
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [30], manifest = Config.NONE)
class WeChatRealtimeTest {
    @Test fun unchangedBubbleGeometryIsRescannedAfterInterval() {
        val sig = "wechat:chat:bubble-bounds"
        assertFalse(OcrRefreshPolicy.shouldCapture(sig, sig, 2_000L, 1_000L))
        assertTrue(OcrRefreshPolicy.shouldCapture(sig, sig, 3_600L, 1_000L))
        assertTrue(OcrRefreshPolicy.shouldCapture("new", sig, 1_100L, 1_000L))
    }

    @Test fun headerOcrSelectsCenteredConversationAboveBubbles() {
        val lines = listOf(
            OcrLine("微信", Rect(520, 20, 620, 55)),
            OcrLine("小雨（4）", Rect(460, 75, 650, 125)),
            OcrLine("今天好吗？", Rect(450, 220, 800, 260)),
        )
        assertEquals("小雨（4）", WeChatTitleOcr.pick(lines, 1080, 190))
        assertNull(WeChatTitleOcr.pick(lines, 1080, 70))
    }
}
