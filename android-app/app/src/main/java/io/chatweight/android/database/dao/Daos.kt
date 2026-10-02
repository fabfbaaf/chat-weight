package io.chatweight.android.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Upsert
import io.chatweight.android.database.entity.*

@Dao interface PersonDao {
    @Upsert fun upsert(value: PersonEntity)
    @Query("SELECT * FROM persons WHERE id = :id LIMIT 1") fun get(id: String): PersonEntity?
    @Query("SELECT * FROM persons ORDER BY updated_at DESC") fun all(): List<PersonEntity>
    @Query("SELECT COUNT(*) FROM persons") fun count(): Long
    @Query("DELETE FROM persons WHERE id = :id") fun delete(id: String): Int
    @Insert(onConflict = OnConflictStrategy.IGNORE) fun insertIdentity(value: PlatformIdentityEntity): Long
}

@Dao interface ConversationDao {
    @Upsert fun upsert(value: ConversationEntity)
    @Query("SELECT * FROM conversations WHERE id = :id LIMIT 1") fun get(id: String): ConversationEntity?
    @Query("SELECT COUNT(*) FROM conversations") fun count(): Long
    @Query("DELETE FROM conversations WHERE id = :id") fun delete(id: String): Int
}

@Dao interface MessageDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE) fun insert(value: MessageEntity): Long
    @Query("SELECT * FROM messages WHERE conversation_id = :conversationId ORDER BY message_time DESC LIMIT :limit")
    fun recent(conversationId: String, limit: Int): List<MessageEntity>
    @Query("SELECT * FROM messages WHERE conversation_id = :conversationId AND id != :id ORDER BY message_time DESC LIMIT 1")
    fun previous(conversationId: String, id: String): MessageEntity?
    @Query("SELECT COUNT(*) FROM messages") fun count(): Long
}

@Dao interface SessionDao {
    @Upsert fun upsert(value: ChatSessionEntity)
    @Query("SELECT * FROM chat_sessions WHERE conversation_id = :conversationId ORDER BY last_message_at DESC LIMIT 1")
    fun latest(conversationId: String): ChatSessionEntity?
    @Query("SELECT COUNT(*) FROM chat_sessions WHERE primary_person_id = :personId AND started_at >= :since AND message_count >= 2")
    fun validCountSince(personId: String, since: Long): Long
}

@Dao interface WeightEventDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE) fun insert(value: WeightEventEntity): Long
    @Query("SELECT COUNT(*) FROM weight_events WHERE session_id = :sessionId AND person_id = :personId AND actor_side = :actor AND event_type = :eventType")
    fun countInSession(sessionId: String, personId: String, actor: String, eventType: String): Long
    @Query("SELECT COUNT(*) FROM weight_events WHERE session_id = :sessionId AND person_id = :personId AND actor_side = :actor AND repeat_group = :repeatGroup")
    fun countRepeat(sessionId: String, personId: String, actor: String, repeatGroup: String): Long
    @Query("SELECT COALESCE(SUM(effective_delta),0) FROM weight_events WHERE person_id = :personId AND actor_side = :actor AND dimension = :dimension AND event_time >= :start AND event_time < :end AND effective_delta > 0")
    fun positiveUsed(personId: String, actor: String, dimension: String, start: Long, end: Long): Double
    @Query("SELECT COALESCE(SUM(effective_delta),0) FROM weight_events WHERE person_id = :personId AND actor_side = :actor AND dimension = :dimension AND event_time >= :start AND event_time < :end AND effective_delta < 0")
    fun negativeUsed(personId: String, actor: String, dimension: String, start: Long, end: Long): Double
    @Query("SELECT COUNT(*) FROM weight_events WHERE person_id = :personId") fun count(personId: String): Long
}

@Dao interface WeightStateDao {
    @Upsert fun upsert(value: WeightStateEntity)
    @Query("SELECT * FROM weight_state WHERE person_id = :personId AND actor_side = :actor AND dimension = :dimension LIMIT 1")
    fun get(personId: String, actor: String, dimension: String): WeightStateEntity?
}

@Dao interface DailyMetricsDao {
    @Upsert fun upsert(value: DailyMetricsEntity)
    @Query("SELECT * FROM daily_metrics WHERE person_id = :personId AND local_date = :date LIMIT 1")
    fun get(personId: String, date: String): DailyMetricsEntity?
    @Query("SELECT COUNT(*) FROM daily_metrics WHERE person_id = :personId AND local_date >= :since AND incoming_messages + outgoing_messages > 0")
    fun activeDaysSince(personId: String, since: String): Long
}

@Dao interface RelationshipProfileDao {
    @Upsert fun upsert(value: RelationshipProfileEntity)
    @Query("SELECT * FROM relationship_profile WHERE person_id = :personId LIMIT 1")
    fun get(personId: String): RelationshipProfileEntity?
}

@Dao interface RelationshipEventDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE) fun insert(value: RelationshipEventEntity): Long
    @Query("SELECT COUNT(*) FROM relationship_events WHERE person_id = :personId AND event_type = :eventType AND event_time >= :start AND event_time < :end")
    fun countInDay(personId: String, eventType: String, start: Long, end: Long): Long
    @Query("SELECT COUNT(*) FROM relationship_events WHERE person_id = :personId AND session_id = :sessionId AND event_type = :eventType")
    fun countInSession(personId: String, sessionId: String, eventType: String): Long
    @Query("SELECT * FROM relationship_events WHERE person_id = :personId AND event_time >= :since ORDER BY event_time DESC")
    fun since(personId: String, since: Long): List<RelationshipEventEntity>
}

@Dao interface RelationshipCandidateDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE) fun insert(value: RelationshipEventCandidateEntity): Long
    @Query("SELECT * FROM relationship_event_candidates WHERE id = :id LIMIT 1")
    fun get(id: String): RelationshipEventCandidateEntity?
    @Query("SELECT * FROM relationship_event_candidates WHERE status = 'pending' ORDER BY event_time DESC LIMIT :limit")
    fun pending(limit: Int): List<RelationshipEventCandidateEntity>
    @Query("UPDATE relationship_event_candidates SET status = :status, reviewed_at = :at WHERE id = :id AND status = 'pending'")
    fun changePending(id: String, status: String, at: Long): Int
}

@Dao interface SnapshotDao {
    @Upsert fun upsertWeight(value: DailyWeightSnapshotEntity)
    @Upsert fun upsertRelationship(value: RelationshipDailySnapshotEntity)
    @Query("SELECT * FROM daily_weight_snapshots WHERE person_id = :personId AND actor_side = :actor ORDER BY local_date DESC LIMIT 1")
    fun latestWeight(personId: String, actor: String): DailyWeightSnapshotEntity?
    @Query("SELECT * FROM relationship_daily_snapshot WHERE person_id = :personId ORDER BY local_date DESC LIMIT 1")
    fun latestRelationship(personId: String): RelationshipDailySnapshotEntity?
}

@Dao interface CaptureCursorDao {
    @Upsert fun upsert(value: CaptureCursorEntity)
    @Query("SELECT * FROM capture_cursors WHERE conversation_id = :conversationId LIMIT 1")
    fun get(conversationId: String): CaptureCursorEntity?
}

@Dao interface AlgorithmMetaDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE) fun insert(value: AlgorithmMetaEntity): Long
}
