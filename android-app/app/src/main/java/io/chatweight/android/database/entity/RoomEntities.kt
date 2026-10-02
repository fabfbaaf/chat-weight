package io.chatweight.android.database.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index

// Generated from sql/schema.sql. Edit that schema and rerun scripts/generate_room_entities.py.
@Entity(
    tableName = "persons",
    primaryKeys = ["id"]
)
data class PersonEntity(
    @ColumnInfo(name = "id") val id: String = "",
    @ColumnInfo(name = "display_name") val displayName: String = "",
    @ColumnInfo(name = "created_at") val createdAt: Long = 0L,
    @ColumnInfo(name = "updated_at") val updatedAt: Long = 0L,
)

@Entity(
    tableName = "platform_identities",
    primaryKeys = ["id"],
    foreignKeys = [ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["person_id"], onDelete = ForeignKey.CASCADE)],
    indices = [Index(value = ["person_id"], name = "idx_identity_person", unique = false), Index(value = ["platform", "platform_user_id"], name = "idx_identity_platform_user", unique = false)]
)
data class PlatformIdentityEntity(
    @ColumnInfo(name = "id") val id: String = "",
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "platform") val platform: String = "",
    @ColumnInfo(name = "platform_user_id") val platformUserId: String? = null,
    @ColumnInfo(name = "display_name") val displayName: String? = null,
    @ColumnInfo(name = "alias") val alias: String? = null,
    @ColumnInfo(name = "created_at") val createdAt: Long = 0L,
)

@Entity(
    tableName = "conversations",
    primaryKeys = ["id"],
    foreignKeys = [ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["primary_person_id"], onDelete = ForeignKey.SET_NULL)],
    indices = [Index(value = ["primary_person_id"], name = "idx_conversations_primary_person_room", unique = false)]
)
data class ConversationEntity(
    @ColumnInfo(name = "id") val id: String = "",
    @ColumnInfo(name = "platform") val platform: String = "",
    @ColumnInfo(name = "platform_conversation_id") val platformConversationId: String? = null,
    @ColumnInfo(name = "title") val title: String? = null,
    @ColumnInfo(name = "conversation_type") val conversationType: String = "",
    @ColumnInfo(name = "primary_person_id") val primaryPersonId: String? = null,
    @ColumnInfo(name = "first_seen_at") val firstSeenAt: Long = 0L,
    @ColumnInfo(name = "last_seen_at") val lastSeenAt: Long = 0L,
)

@Entity(
    tableName = "messages",
    primaryKeys = ["id"],
    foreignKeys = [ForeignKey(entity = ConversationEntity::class, parentColumns = ["id"], childColumns = ["conversation_id"], onDelete = ForeignKey.CASCADE), ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["person_id"], onDelete = ForeignKey.SET_NULL)],
    indices = [Index(value = ["conversation_id", "message_time"], name = "idx_messages_conversation_time", unique = false), Index(value = ["person_id", "message_time"], name = "idx_messages_person_time", unique = false), Index(value = ["conversation_id", "direction", "message_time"], name = "idx_messages_direction_time", unique = false), Index(value = ["platform", "conversation_id", "fingerprint"], name = "idx_messages_fingerprint", unique = true)]
)
data class MessageEntity(
    @ColumnInfo(name = "id") val id: String = "",
    @ColumnInfo(name = "platform") val platform: String = "",
    @ColumnInfo(name = "account_id") val accountId: String? = null,
    @ColumnInfo(name = "conversation_id") val conversationId: String = "",
    @ColumnInfo(name = "person_id") val personId: String? = null,
    @ColumnInfo(name = "sender_id") val senderId: String? = null,
    @ColumnInfo(name = "sender_name") val senderName: String? = null,
    @ColumnInfo(name = "direction") val direction: String = "",
    @ColumnInfo(name = "message_type") val messageType: String = "",
    @ColumnInfo(name = "text") val text: String? = null,
    @ColumnInfo(name = "message_time") val messageTime: Long = 0L,
    @ColumnInfo(name = "captured_at") val capturedAt: Long = 0L,
    @ColumnInfo(name = "voice_duration_ms") val voiceDurationMs: Long? = null,
    @ColumnInfo(name = "reply_to_message_id") val replyToMessageId: String? = null,
    @ColumnInfo(name = "fingerprint") val fingerprint: String = "",
    @ColumnInfo(name = "capture_source") val captureSource: String = "",
    @ColumnInfo(name = "confidence") val confidence: Double = 0.0,
    @ColumnInfo(name = "raw_json") val rawJson: String? = null,
)

@Entity(
    tableName = "chat_sessions",
    primaryKeys = ["id"],
    foreignKeys = [ForeignKey(entity = ConversationEntity::class, parentColumns = ["id"], childColumns = ["conversation_id"], onDelete = ForeignKey.CASCADE)],
    indices = [Index(value = ["conversation_id", "started_at"], name = "idx_sessions_conversation_start", unique = false), Index(value = ["primary_person_id", "started_at"], name = "idx_sessions_person_start", unique = false)]
)
data class ChatSessionEntity(
    @ColumnInfo(name = "id") val id: String = "",
    @ColumnInfo(name = "conversation_id") val conversationId: String = "",
    @ColumnInfo(name = "primary_person_id") val primaryPersonId: String? = null,
    @ColumnInfo(name = "started_at") val startedAt: Long = 0L,
    @ColumnInfo(name = "ended_at") val endedAt: Long? = null,
    @ColumnInfo(name = "initiator_side") val initiatorSide: String = "",
    @ColumnInfo(name = "message_count") val messageCount: Long = 0L,
    @ColumnInfo(name = "incoming_count") val incomingCount: Long = 0L,
    @ColumnInfo(name = "outgoing_count") val outgoingCount: Long = 0L,
    @ColumnInfo(name = "turn_count") val turnCount: Long = 0L,
    @ColumnInfo(name = "duration_ms") val durationMs: Long = 0L,
    @ColumnInfo(name = "last_message_at") val lastMessageAt: Long = 0L,
    @ColumnInfo(name = "close_reason") val closeReason: String? = null,
)

@Entity(
    tableName = "weight_events",
    primaryKeys = ["id"],
    foreignKeys = [ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["person_id"], onDelete = ForeignKey.CASCADE)],
    indices = [Index(value = ["person_id", "event_time"], name = "idx_weight_events_person_time", unique = false), Index(value = ["person_id", "actor_side", "dimension", "event_time"], name = "idx_weight_events_person_dimension", unique = false), Index(value = ["session_id", "event_type"], name = "idx_weight_events_session", unique = false)]
)
data class WeightEventEntity(
    @ColumnInfo(name = "id") val id: String = "",
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "conversation_id") val conversationId: String = "",
    @ColumnInfo(name = "session_id") val sessionId: String? = null,
    @ColumnInfo(name = "actor_side") val actorSide: String = "",
    @ColumnInfo(name = "event_type") val eventType: String = "",
    @ColumnInfo(name = "dimension") val dimension: String = "",
    @ColumnInfo(name = "base_delta") val baseDelta: Double = 0.0,
    @ColumnInfo(name = "repeat_multiplier") val repeatMultiplier: Double = 0.0,
    @ColumnInfo(name = "confidence_multiplier") val confidenceMultiplier: Double = 0.0,
    @ColumnInfo(name = "cap_multiplier") val capMultiplier: Double = 0.0,
    @ColumnInfo(name = "effective_delta") val effectiveDelta: Double = 0.0,
    @ColumnInfo(name = "event_time") val eventTime: Long = 0L,
    @ColumnInfo(name = "repeat_group") val repeatGroup: String? = null,
    @ColumnInfo(name = "source_message_ids_json") val sourceMessageIdsJson: String? = null,
    @ColumnInfo(name = "metadata_json") val metadataJson: String? = null,
    @ColumnInfo(name = "created_at") val createdAt: Long = 0L,
)

@Entity(
    tableName = "weight_state",
    primaryKeys = ["person_id", "actor_side", "dimension"],
    foreignKeys = [ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["person_id"], onDelete = ForeignKey.CASCADE)]
)
data class WeightStateEntity(
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "actor_side") val actorSide: String = "",
    @ColumnInfo(name = "dimension") val dimension: String = "",
    @ColumnInfo(name = "recent_raw") val recentRaw: Double = 0.0,
    @ColumnInfo(name = "base_raw") val baseRaw: Double = 0.0,
    @ColumnInfo(name = "updated_at") val updatedAt: Long = 0L,
)

@Entity(
    tableName = "daily_metrics",
    primaryKeys = ["person_id", "local_date"]
)
data class DailyMetricsEntity(
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "local_date") val localDate: String = "",
    @ColumnInfo(name = "incoming_messages") val incomingMessages: Long = 0L,
    @ColumnInfo(name = "outgoing_messages") val outgoingMessages: Long = 0L,
    @ColumnInfo(name = "incoming_chars") val incomingChars: Long = 0L,
    @ColumnInfo(name = "outgoing_chars") val outgoingChars: Long = 0L,
    @ColumnInfo(name = "session_count") val sessionCount: Long = 0L,
    @ColumnInfo(name = "self_started_sessions") val selfStartedSessions: Long = 0L,
    @ColumnInfo(name = "other_started_sessions") val otherStartedSessions: Long = 0L,
    @ColumnInfo(name = "total_turns") val totalTurns: Long = 0L,
    @ColumnInfo(name = "self_avg_reply_ms") val selfAvgReplyMs: Long? = null,
    @ColumnInfo(name = "other_avg_reply_ms") val otherAvgReplyMs: Long? = null,
    @ColumnInfo(name = "active_minutes") val activeMinutes: Long = 0L,
)

@Entity(
    tableName = "daily_weight_snapshots",
    primaryKeys = ["person_id", "local_date", "actor_side"]
)
data class DailyWeightSnapshotEntity(
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "local_date") val localDate: String = "",
    @ColumnInfo(name = "actor_side") val actorSide: String = "",
    @ColumnInfo(name = "initiative_score") val initiativeScore: Double = 0.0,
    @ColumnInfo(name = "response_score") val responseScore: Double = 0.0,
    @ColumnInfo(name = "effort_score") val effortScore: Double = 0.0,
    @ColumnInfo(name = "continuity_score") val continuityScore: Double = 0.0,
    @ColumnInfo(name = "frequency_score") val frequencyScore: Double = 0.0,
    @ColumnInfo(name = "overall_score") val overallScore: Double = 0.0,
    @ColumnInfo(name = "recent_raw_total") val recentRawTotal: Double = 0.0,
    @ColumnInfo(name = "base_raw_total") val baseRawTotal: Double = 0.0,
    @ColumnInfo(name = "confidence_score") val confidenceScore: Double = 0.0,
    @ColumnInfo(name = "calculated_at") val calculatedAt: Long = 0L,
)

@Entity(
    tableName = "relationship_profile",
    primaryKeys = ["person_id"],
    foreignKeys = [ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["person_id"], onDelete = ForeignKey.CASCADE)]
)
data class RelationshipProfileEntity(
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "relationship_type") val relationshipType: String = "",
    @ColumnInfo(name = "custom_label") val customLabel: String? = null,
    @ColumnInfo(name = "expression_stage") val expressionStage: Long = 0L,
    @ColumnInfo(name = "highest_expression_stage") val highestExpressionStage: Long = 0L,
    @ColumnInfo(name = "expression_raw") val expressionRaw: Double = 0.0,
    @ColumnInfo(name = "expression_heat_raw") val expressionHeatRaw: Double = 0.0,
    @ColumnInfo(name = "heat_updated_at") val heatUpdatedAt: Long = 0L,
    @ColumnInfo(name = "manually_confirmed_stage") val manuallyConfirmedStage: Long? = null,
    @ColumnInfo(name = "last_relationship_event_at") val lastRelationshipEventAt: Long? = null,
    @ColumnInfo(name = "engine_version") val engineVersion: Long = 0L,
    @ColumnInfo(name = "created_at") val createdAt: Long = 0L,
    @ColumnInfo(name = "updated_at") val updatedAt: Long = 0L,
)

@Entity(
    tableName = "relationship_events",
    primaryKeys = ["id"],
    foreignKeys = [ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["person_id"], onDelete = ForeignKey.CASCADE), ForeignKey(entity = ConversationEntity::class, parentColumns = ["id"], childColumns = ["conversation_id"], onDelete = ForeignKey.SET_NULL), ForeignKey(entity = ChatSessionEntity::class, parentColumns = ["id"], childColumns = ["session_id"], onDelete = ForeignKey.SET_NULL)],
    indices = [Index(value = ["person_id", "event_time"], name = "idx_relationship_events_person_time", unique = false), Index(value = ["person_id", "event_type", "event_time"], name = "idx_relationship_events_person_type", unique = false), Index(value = ["person_id", "event_category", "event_time"], name = "idx_relationship_events_category", unique = false), Index(value = ["session_id"], name = "idx_relationship_events_session", unique = false), Index(value = ["person_id", "dedupe_key"], name = "idx_relationship_events_dedupe", unique = true), Index(value = ["conversation_id"], name = "idx_relationship_events_conversation_room", unique = false)]
)
data class RelationshipEventEntity(
    @ColumnInfo(name = "id") val id: String = "",
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "conversation_id") val conversationId: String? = null,
    @ColumnInfo(name = "session_id") val sessionId: String? = null,
    @ColumnInfo(name = "actor_side") val actorSide: String = "",
    @ColumnInfo(name = "event_type") val eventType: String = "",
    @ColumnInfo(name = "event_category") val eventCategory: String = "",
    @ColumnInfo(name = "source") val source: String = "",
    @ColumnInfo(name = "base_progress_delta") val baseProgressDelta: Double = 0.0,
    @ColumnInfo(name = "base_heat_delta") val baseHeatDelta: Double = 0.0,
    @ColumnInfo(name = "repeat_multiplier") val repeatMultiplier: Double = 0.0,
    @ColumnInfo(name = "confidence") val confidence: Double = 0.0,
    @ColumnInfo(name = "effective_progress_delta") val effectiveProgressDelta: Double = 0.0,
    @ColumnInfo(name = "effective_heat_delta") val effectiveHeatDelta: Double = 0.0,
    @ColumnInfo(name = "event_time") val eventTime: Long = 0L,
    @ColumnInfo(name = "source_message_ids_json") val sourceMessageIdsJson: String? = null,
    @ColumnInfo(name = "metadata_json") val metadataJson: String? = null,
    @ColumnInfo(name = "dedupe_key") val dedupeKey: String? = null,
    @ColumnInfo(name = "engine_version") val engineVersion: Long = 0L,
    @ColumnInfo(name = "created_at") val createdAt: Long = 0L,
)

@Entity(
    tableName = "relationship_daily_snapshot",
    primaryKeys = ["person_id", "local_date"],
    foreignKeys = [ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["person_id"], onDelete = ForeignKey.CASCADE)]
)
data class RelationshipDailySnapshotEntity(
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "local_date") val localDate: String = "",
    @ColumnInfo(name = "relationship_type") val relationshipType: String = "",
    @ColumnInfo(name = "expression_stage") val expressionStage: Long = 0L,
    @ColumnInfo(name = "highest_expression_stage") val highestExpressionStage: Long = 0L,
    @ColumnInfo(name = "expression_raw") val expressionRaw: Double = 0.0,
    @ColumnInfo(name = "expression_progress_score") val expressionProgressScore: Double = 0.0,
    @ColumnInfo(name = "expression_heat_raw") val expressionHeatRaw: Double = 0.0,
    @ColumnInfo(name = "expression_heat_score") val expressionHeatScore: Double = 0.0,
    @ColumnInfo(name = "familiarity_event_count") val familiarityEventCount: Long = 0L,
    @ColumnInfo(name = "approach_event_count") val approachEventCount: Long = 0L,
    @ColumnInfo(name = "care_event_count") val careEventCount: Long = 0L,
    @ColumnInfo(name = "affection_event_count") val affectionEventCount: Long = 0L,
    @ColumnInfo(name = "direct_expression_count") val directExpressionCount: Long = 0L,
    @ColumnInfo(name = "retreat_event_count") val retreatEventCount: Long = 0L,
    @ColumnInfo(name = "valid_session_count") val validSessionCount: Long = 0L,
    @ColumnInfo(name = "calculated_at") val calculatedAt: Long = 0L,
    @ColumnInfo(name = "engine_version") val engineVersion: Long = 0L,
)

@Entity(
    tableName = "algorithm_meta",
    primaryKeys = ["key"]
)
data class AlgorithmMetaEntity(
    @ColumnInfo(name = "key") val key: String = "",
    @ColumnInfo(name = "value") val value: String = "",
)

@Entity(
    tableName = "relationship_event_candidates",
    primaryKeys = ["id"],
    foreignKeys = [ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["person_id"], onDelete = ForeignKey.CASCADE)],
    indices = [Index(value = ["person_id", "dedupe_key"], name = "idx_relationship_candidates_dedupe", unique = true), Index(value = ["status", "event_time"], name = "idx_relationship_candidates_pending", unique = false)]
)
data class RelationshipEventCandidateEntity(
    @ColumnInfo(name = "id") val id: String = "",
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "conversation_id") val conversationId: String = "",
    @ColumnInfo(name = "session_id") val sessionId: String? = null,
    @ColumnInfo(name = "actor_side") val actorSide: String = "",
    @ColumnInfo(name = "event_type") val eventType: String = "",
    @ColumnInfo(name = "source") val source: String = "",
    @ColumnInfo(name = "confidence") val confidence: Double = 0.0,
    @ColumnInfo(name = "confirmation_policy") val confirmationPolicy: String = "",
    @ColumnInfo(name = "status") val status: String = "",
    @ColumnInfo(name = "event_time") val eventTime: Long = 0L,
    @ColumnInfo(name = "source_message_ids_json") val sourceMessageIdsJson: String? = null,
    @ColumnInfo(name = "evidence_text") val evidenceText: String? = null,
    @ColumnInfo(name = "reason_code") val reasonCode: String? = null,
    @ColumnInfo(name = "metadata_json") val metadataJson: String? = null,
    @ColumnInfo(name = "dedupe_key") val dedupeKey: String = "",
    @ColumnInfo(name = "created_at") val createdAt: Long = 0L,
    @ColumnInfo(name = "reviewed_at") val reviewedAt: Long? = null,
)

@Entity(
    tableName = "person_special_nicknames",
    primaryKeys = ["person_id", "nickname"],
    foreignKeys = [ForeignKey(entity = PersonEntity::class, parentColumns = ["id"], childColumns = ["person_id"], onDelete = ForeignKey.CASCADE)]
)
data class PersonSpecialNicknameEntity(
    @ColumnInfo(name = "person_id") val personId: String = "",
    @ColumnInfo(name = "nickname") val nickname: String = "",
    @ColumnInfo(name = "created_at") val createdAt: Long = 0L,
)

