package io.chatweight.android

import android.graphics.Color
import android.os.Bundle
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import io.chatweight.android.database.ChatWeightRoom
import io.chatweight.android.database.entity.PersonEntity
import io.chatweight.android.database.entity.RelationshipProfileEntity
import io.chatweight.android.pipeline.ChatWeightPipeline
import io.chatweight.core.RelationshipType
import java.util.concurrent.Executors

/** Simple read and edit view for the local relationship state. */
class ContactsActivity : AppCompatActivity() {
    private val worker = Executors.newSingleThreadExecutor()
    private lateinit var list: LinearLayout
    private val db by lazy { ChatWeightRoom.get(applicationContext) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "ChatWeight 联系人"
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 24, 24, 24) }
        setContentView(ScrollView(this).apply { addView(list) })
    }

    override fun onResume() { super.onResume(); refresh() }
    override fun onDestroy() { worker.shutdown(); super.onDestroy() }

    private fun refresh() {
        worker.execute {
            val rows = runCatching { db.people().all().map { person ->
                ContactRow(person, db.relationshipProfiles().get(person.id),
                    db.snapshots().latestWeight(person.id, "self")?.overallScore ?: 0.0,
                    db.snapshots().latestWeight(person.id, "other")?.overallScore ?: 0.0)
            } }.getOrDefault(emptyList())
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                list.removeAllViews()
                list.addView(line("联系人 · ${rows.size}", 22f, true))
                if (rows.isEmpty()) list.addView(line("采集到新消息后，联系人会出现在这里。", 14f))
                rows.forEach { row ->
                    val type = row.profile?.relationshipType ?: "friend"
                    val stage = row.profile?.expressionStage ?: 0L
                    val item = line("${row.person.displayName}\n关系：${type.uppercase()} · Stage $stage\n我的投入 ${row.self.toInt()} · 对方投入 ${row.other.toInt()}\n点击设置关系类型", 15f)
                    item.setPadding(20, 22, 20, 22)
                    item.setBackgroundColor(Color.WHITE)
                    item.setOnClickListener { chooseType(row.person) }
                    list.addView(item, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 16 })
                }
            }
        }
    }

    private fun chooseType(person: PersonEntity) {
        val types = RelationshipType.entries.toTypedArray()
        AlertDialog.Builder(this).setTitle("${person.displayName} 的关系类型")
            .setItems(types.map { it.name }.toTypedArray()) { _, index ->
                worker.execute {
                    runCatching { db.runInTransaction { ChatWeightPipeline(db).setRelationshipType(person.id, types[index]) } }
                    runOnUiThread { if (!isFinishing && !isDestroyed) refresh() }
                }
            }.show()
    }

    private fun line(value: String, size: Float, bold: Boolean = false) = TextView(this).apply {
        text = value; textSize = size; setTextColor(Color.rgb(25, 34, 49))
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }

    private data class ContactRow(
        val person: PersonEntity, val profile: RelationshipProfileEntity?, val self: Double, val other: Double
    )
}
