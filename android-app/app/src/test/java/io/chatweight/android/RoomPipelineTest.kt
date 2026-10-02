package io.chatweight.android

import androidx.room.Room
import io.chatweight.android.database.ChatWeightRoom
import io.chatweight.android.core.Prefs
import io.chatweight.android.core.ChatSnapshot
import io.chatweight.android.core.Msg
import io.chatweight.android.database.entity.ConversationEntity
import io.chatweight.android.database.entity.MessageEntity
import io.chatweight.android.database.entity.PersonEntity
import io.chatweight.android.pipeline.ChatWeightPipeline
import io.chatweight.android.reply.ReplyAssistant
import io.chatweight.core.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [30], manifest = Config.NONE)
class RoomPipelineTest {
    private lateinit var db: ChatWeightRoom
    private lateinit var pipeline: ChatWeightPipeline
    private val personId = "qq:android:person:test"
    private val conversationId = "qq:android:conversation:test"

    @Before fun open() {
        db = Room.inMemoryDatabaseBuilder(RuntimeEnvironment.getApplication(), ChatWeightRoom::class.java)
            .allowMainThreadQueries().build()
        pipeline = ChatWeightPipeline(db)
        db.people().upsert(PersonEntity(personId, "小雨", 1L, 1L))
        db.conversations().upsert(ConversationEntity(conversationId, "qq", title = "小雨",
            conversationType = "private", primaryPersonId = personId, firstSeenAt = 1L, lastSeenAt = 1L))
    }
    @After fun close() = db.close()

    private fun message(id: String, text: String, time: Long, direction: MessageDirection = MessageDirection.OUTGOING): UnifiedMessage =
        UnifiedMessage(id, Platform.QQ, conversationId, direction, MessageType.TEXT, time, time,
            "fingerprint:$id", personId = personId, text = text)

    private fun ingest(value: UnifiedMessage) {
        db.runInTransaction {
            val inserted = db.messages().insert(MessageEntity(id = value.id, platform = "qq", conversationId = conversationId,
                personId = personId, direction = value.direction.name.lowercase(), messageType = "text", text = value.text,
                messageTime = value.messageTime, capturedAt = value.capturedAt, fingerprint = value.fingerprint,
                captureSource = "test", confidence = 1.0))
            if (inserted != -1L) pipeline.process(value)
        }
    }

    @Test fun roomFingerprintSessionAndDailySnapshot() {
        val first = message("m1", "你好", 1_000_000L)
        val second = message("m2", "你好", 1_060_000L, MessageDirection.INCOMING)
        ingest(first)
        ingest(second)
        ingest(second)
        assertEquals(2L, db.messages().count())
        assertEquals(2L, db.sessions().latest(conversationId)?.messageCount)
        assertNotNull(db.snapshots().latestWeight(personId, "self"))
        assertNotNull(db.snapshots().latestRelationship(personId))
        assertTrue(db.weightEvents().count(personId) > 0)
        assertEquals(-1L, db.messages().insert(MessageEntity(id = "m3", platform = "qq",
            conversationId = conversationId, direction = "incoming", messageType = "text",
            messageTime = 1_060_000L, capturedAt = 1_060_000L, fingerprint = second.fingerprint)))
        // The pipeline marker prevents replay from inflating daily metrics.
        pipeline.process(second)
        assertEquals(2L, db.sessions().latest(conversationId)?.messageCount)
    }

    @Test fun sessionRestoresAcrossPipelineInstancesAndSplitsAtThirtyMinutes() {
        ingest(message("m1", "你好", 1_000_000L))
        val original = db.sessions().latest(conversationId)!!.id
        pipeline = ChatWeightPipeline(db)
        ingest(message("m2", "回复", 1_010_000L, MessageDirection.INCOMING))
        assertEquals(original, db.sessions().latest(conversationId)!!.id)
        ingest(message("m3", "稍后", 1_010_000L + SessionManager.GAP_MS))
        assertNotEquals(original, db.sessions().latest(conversationId)!!.id)
    }

    @Test fun directLikeAndRelationshipConfirmationNeedManualReview() {
        pipeline.setRelationshipType(personId, RelationshipType.CRUSH)
        ingest(message("m1", "我喜欢你", 1_000_000L))
        val direct = db.relationshipCandidates().pending(10).single { it.eventType == "direct_like_expression" }
        assertEquals(0L, db.relationshipProfiles().get(personId)!!.expressionStage)
        assertFalse(pipeline.confirmCandidate(direct.id, automatic = true))
        assertTrue(pipeline.confirmCandidate(direct.id))
        assertEquals(5L, db.relationshipProfiles().get(personId)!!.expressionStage)

        ingest(message("m2", "我们在一起吧", 1_060_000L, MessageDirection.INCOMING))
        val confirmed = db.relationshipCandidates().pending(10).single { it.eventType == "possible_relationship_confirmed" }
        assertEquals(5L, db.relationshipProfiles().get(personId)!!.expressionStage)
        assertFalse(pipeline.confirmCandidate(confirmed.id, automatic = true))
        assertTrue(pipeline.rejectCandidate(confirmed.id))
        assertEquals(5L, db.relationshipProfiles().get(personId)!!.expressionStage)
        ingest(message("m3", "那我们算情侣", 1_120_000L, MessageDirection.INCOMING))
        val second = db.relationshipCandidates().pending(10).single { it.eventType == "possible_relationship_confirmed" }
        assertTrue(pipeline.confirmCandidate(second.id))
        assertEquals(6L, db.relationshipProfiles().get(personId)!!.expressionStage)
    }

    @Test fun deletingConversationCascadesMessagesAndSessions() {
        ingest(message("m1", "你好", 1_000_000L))
        assertEquals(1, db.conversations().delete(conversationId))
        assertEquals(0L, db.messages().count())
        assertNull(db.sessions().latest(conversationId))
    }

    @Test fun aiDisabledDoesNotBlockLocalPipeline() {
        val prefs = Prefs(RuntimeEnvironment.getApplication(), "chatweight-test-no-ai")
        prefs.aiReplyEnabled = false
        ingest(message("m1", "你好", 1_000_000L))
        val outcome = ReplyAssistant(prefs).analyze(ChatSnapshot("小雨", listOf(Msg("other", "你好"))), null)
        assertTrue(outcome.candidates.isEmpty())
        assertEquals(1L, db.messages().count())
        assertTrue(db.weightEvents().count(personId) > 0)
    }
}
