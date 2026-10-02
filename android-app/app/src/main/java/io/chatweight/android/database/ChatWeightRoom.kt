package io.chatweight.android.database

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import io.chatweight.android.database.dao.*
import io.chatweight.android.database.entity.*

@Database(
    entities = [
        PersonEntity::class, PlatformIdentityEntity::class, ConversationEntity::class,
        MessageEntity::class, ChatSessionEntity::class, WeightEventEntity::class,
        WeightStateEntity::class, DailyMetricsEntity::class, DailyWeightSnapshotEntity::class,
        RelationshipProfileEntity::class, RelationshipEventEntity::class,
        RelationshipDailySnapshotEntity::class, RelationshipEventCandidateEntity::class,
        PersonSpecialNicknameEntity::class, AlgorithmMetaEntity::class,
        CaptureCursorEntity::class,
    ],
    version = 2,
    exportSchema = true,
)
abstract class ChatWeightRoom : RoomDatabase() {
    abstract fun people(): PersonDao
    abstract fun conversations(): ConversationDao
    abstract fun messages(): MessageDao
    abstract fun sessions(): SessionDao
    abstract fun weightEvents(): WeightEventDao
    abstract fun weightStates(): WeightStateDao
    abstract fun dailyMetrics(): DailyMetricsDao
    abstract fun relationshipProfiles(): RelationshipProfileDao
    abstract fun relationshipEvents(): RelationshipEventDao
    abstract fun relationshipCandidates(): RelationshipCandidateDao
    abstract fun snapshots(): SnapshotDao
    abstract fun captureCursors(): CaptureCursorDao
    abstract fun algorithmMeta(): AlgorithmMetaDao

    companion object {
        const val DATABASE_NAME = "chatweight.db"

        @Volatile private var instance: ChatWeightRoom? = null

        fun get(context: Context): ChatWeightRoom = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext, ChatWeightRoom::class.java, DATABASE_NAME
            ).build().also { instance = it }
        }
    }
}
