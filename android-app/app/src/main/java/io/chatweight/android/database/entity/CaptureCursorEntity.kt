package io.chatweight.android.database.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

/** Last visible screen and sequence counter, persisted across service restarts. */
@Entity(tableName = "capture_cursors")
data class CaptureCursorEntity(
    @PrimaryKey @ColumnInfo(name = "conversation_id") val conversationId: String,
    @ColumnInfo(name = "screen_json") val screenJson: String,
    @ColumnInfo(name = "next_sequence") val nextSequence: Long,
    @ColumnInfo(name = "updated_at") val updatedAt: Long,
)
