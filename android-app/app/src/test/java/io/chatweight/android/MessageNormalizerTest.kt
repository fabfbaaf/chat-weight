package io.chatweight.android

import io.chatweight.android.ingest.CapturedLine
import io.chatweight.android.ingest.MessageNormalizer
import io.chatweight.android.core.ChatSnapshot
import io.chatweight.android.core.Msg
import io.chatweight.core.Platform
import org.junit.Assert.*
import org.junit.Test

class MessageNormalizerTest {
    @Test fun qqAndWeChatBecomeUnifiedMessages() {
        for (platform in listOf(Platform.QQ, Platform.WECHAT)) {
            val result = MessageNormalizer.normalize(platform, "小雨", listOf(
                CapturedLine("other", "你好"), CapturedLine("me", "在呢")
            ), null, 1_000_000L, primeExisting = false)
            assertEquals(2, result.messages.size)
            assertEquals(platform, result.messages[0].platform)
            assertEquals("你好", result.messages[0].text)
            assertEquals("INCOMING", result.messages[0].direction.name)
            assertEquals("OUTGOING", result.messages[1].direction.name)
            assertNotNull(result.messages[0].personId)
            assertEquals(2, result.messages.map { it.fingerprint }.distinct().size)
        }
    }

    @Test fun repeatedEventsDeduplicateButConsecutiveEqualTextSurvives() {
        val first = MessageNormalizer.normalize(Platform.QQ, "小雨",
            listOf(CapturedLine("other", "好")), null, 1_000_000L, primeExisting = false)
        val second = MessageNormalizer.normalize(Platform.QQ, "小雨",
            listOf(CapturedLine("other", "好"), CapturedLine("other", "好")), first.cursor, 1_001_000L)
        val duplicateEvent = MessageNormalizer.normalize(Platform.QQ, "小雨",
            listOf(CapturedLine("other", "好"), CapturedLine("other", "好")), second.cursor, 1_002_000L)
        assertEquals(1, second.messages.size)
        assertTrue(duplicateEvent.messages.isEmpty())
        assertNotEquals(first.messages.single().fingerprint, second.messages.single().fingerprint)
    }

    @Test fun conversationCursorIsIndependent() {
        val a = MessageNormalizer.normalize(Platform.QQ, "甲", listOf(CapturedLine("other", "好")), null,
            1_000_000L, primeExisting = false)
        val b = MessageNormalizer.normalize(Platform.QQ, "乙", listOf(CapturedLine("other", "好")), null,
            1_000_000L, primeExisting = false)
        assertNotEquals(a.conversationId, b.conversationId)
        assertNotEquals(a.messages.single().fingerprint, b.messages.single().fingerprint)
    }

    @Test fun unknownSideNeverBecomesIncoming() {
        val result = MessageNormalizer.normalize(Platform.WECHAT, "小雨", listOf(CapturedLine("unknown", "OCR 文本")),
            null, 1_000_000L, primeExisting = false)
        assertTrue(result.messages.isEmpty())
    }

    @Test fun visibleSignatureChangesForAnotherIdenticalBubble() {
        val one = ChatSnapshot("小雨", listOf(Msg("other", "好")))
        val two = ChatSnapshot("小雨", listOf(Msg("other", "好"), Msg("other", "好")))
        assertNotEquals(one.signature(), two.signature())
    }
}
