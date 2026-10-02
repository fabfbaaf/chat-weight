package io.chatweight.android.ingest

import android.content.Context
import android.util.Log
import io.chatweight.android.database.ChatWeightRoom
import io.chatweight.android.database.entity.CaptureCursorEntity
import io.chatweight.android.database.entity.ConversationEntity
import io.chatweight.android.database.entity.PersonEntity
import io.chatweight.android.database.entity.PlatformIdentityEntity
import io.chatweight.android.pipeline.ChatWeightPipeline
import io.chatweight.android.pipeline.toEntity
import io.chatweight.core.Platform
import org.json.JSONArray
import java.util.concurrent.Callable
import java.util.concurrent.Executors

data class LocalSummary(
    val personId: String,
    val displayName: String,
    val relationshipType: String,
    val expressionStage: Int,
    val selfEngagement: Double,
    val otherEngagement: Double,
    val recentHeat: Double,
)

data class IngestOutcome(val inserted: Int, val summary: LocalSummary?, val error: String? = null)

/** Serializes capture batches and commits messages, derived state and cursor atomically. */
class MessageIngestService(context: Context) {
    private val db = ChatWeightRoom.get(context)
    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "chatweight-ingest").apply { isDaemon = true }
    }
    private val pipeline = ChatWeightPipeline(db)

    fun enqueue(
        platform: Platform,
        title: String?,
        visible: List<CapturedLine>,
        source: String,
        callback: (IngestOutcome) -> Unit = {},
    ) {
        if (title.isNullOrBlank()) return
        executor.execute {
            try {
                val outcome = db.runInTransaction(Callable { ingest(platform, title, visible, source) })
                callback(outcome)
            } catch (error: Exception) {
                Log.w(TAG, "ingest failed: ${error.javaClass.simpleName}")
                callback(IngestOutcome(0, null, error.javaClass.simpleName))
            }
        }
    }

    private fun ingest(platform: Platform, title: String, visible: List<CapturedLine>, source: String): IngestOutcome {
        val now = System.currentTimeMillis()
        val cid = MessageNormalizer.conversationId(platform, title)
        val previous = db.captureCursors().get(cid)?.let { stored ->
            ScreenCursor(jsonStrings(stored.screenJson), stored.nextSequence)
        }
        val batch = MessageNormalizer.normalize(platform, title, visible, previous, now, source)
        val people = batch.messages.mapNotNull { message ->
            message.personId?.let { id -> id to (message.senderName?.takeIf { message.direction.name == "INCOMING" }
                ?: batch.conversationTitle) }
        }.toMap()
        for ((id, name) in people) {
            val existing = db.people().get(id)
            db.people().upsert(PersonEntity(id, name, existing?.createdAt ?: now, now))
            db.people().insertIdentity(PlatformIdentityEntity(
                id = "identity:${MessageFingerprint.sha256(id).take(24)}", personId = id,
                platform = platform.name.lowercase(), displayName = name, alias = name, createdAt = now,
            ))
        }
        if (batch.primaryPersonId != null && db.people().get(batch.primaryPersonId) == null) {
            val id = batch.primaryPersonId
            db.people().upsert(PersonEntity(id, batch.conversationTitle, now, now))
        }
        val oldConversation = db.conversations().get(cid)
        db.conversations().upsert(ConversationEntity(
            id = cid, platform = platform.name.lowercase(), title = batch.conversationTitle,
            conversationType = batch.conversationType, primaryPersonId = batch.primaryPersonId,
            firstSeenAt = oldConversation?.firstSeenAt ?: now, lastSeenAt = now,
        ))
        var inserted = 0
        for (message in batch.messages) {
            if (db.messages().insert(message.toEntity()) != -1L) {
                inserted++
                pipeline.process(message)
            }
        }
        db.captureCursors().upsert(CaptureCursorEntity(
            conversationId = cid, screenJson = JSONArray(batch.cursor.keys).toString(),
            nextSequence = batch.cursor.nextSequence, updatedAt = now,
        ))
        val personId = batch.primaryPersonId ?: batch.messages.lastOrNull { it.personId != null }?.personId
        val summary = personId?.let { pid ->
            val profile = db.relationshipProfiles().get(pid)
            LocalSummary(
                personId = pid, displayName = db.people().get(pid)?.displayName ?: batch.conversationTitle,
                relationshipType = profile?.relationshipType ?: "friend",
                expressionStage = profile?.expressionStage?.toInt() ?: 0,
                selfEngagement = db.snapshots().latestWeight(pid, "self")?.overallScore ?: 0.0,
                otherEngagement = db.snapshots().latestWeight(pid, "other")?.overallScore ?: 0.0,
                recentHeat = db.snapshots().latestRelationship(pid)?.expressionHeatScore ?: 0.0,
            )
        }
        return IngestOutcome(inserted, summary)
    }

    fun shutdown() = executor.shutdown()

    private fun jsonStrings(value: String): List<String> = runCatching {
        JSONArray(value).let { array -> (0 until array.length()).map { array.getString(it) } }
    }.getOrDefault(emptyList())

    companion object { private const val TAG = "ChatWeightIngest" }
}
