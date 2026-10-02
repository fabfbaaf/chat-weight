package io.chatweight.android

import android.graphics.Color
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import io.chatweight.android.database.ChatWeightRoom
import io.chatweight.android.pipeline.ChatWeightPipeline
import java.util.concurrent.Executors

/** Manual review gate for high-impact relationship events. */
class ReviewActivity : AppCompatActivity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val db by lazy { ChatWeightRoom.get(applicationContext) }
    private lateinit var list: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Review Center"
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 24, 24, 24) }
        setContentView(ScrollView(this).apply { addView(list) })
    }

    override fun onResume() { super.onResume(); refresh() }
    override fun onDestroy() { worker.shutdown(); super.onDestroy() }

    private fun refresh() {
        worker.execute {
            val pending = runCatching { db.relationshipCandidates().pending(100).map { candidate ->
                candidate to (db.people().get(candidate.personId)?.displayName ?: "未知联系人")
            } }.getOrDefault(emptyList())
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                list.removeAllViews()
                list.addView(TextView(this).apply { text = "待审核 · ${pending.size}"; textSize = 22f })
                if (pending.isEmpty()) list.addView(TextView(this).apply { text = "暂无待审核关系事件"; textSize = 15f })
                pending.forEach { (candidate, name) ->
                    val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 18, 18, 18); setBackgroundColor(Color.WHITE) }
                    card.addView(TextView(this).apply {
                        text = "$name · ${candidate.eventType}\n${candidate.evidenceText.orEmpty()}\n置信度 ${(candidate.confidence * 100).toInt()}%"
                        textSize = 15f
                    })
                    val buttons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
                    buttons.addView(Button(this).apply { text = "确认"; setOnClickListener { decide(candidate.id, true) } })
                    buttons.addView(Button(this).apply { text = "拒绝"; setOnClickListener { decide(candidate.id, false) } })
                    card.addView(buttons)
                    list.addView(card, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 16 })
                }
            }
        }
    }

    private fun decide(id: String, confirm: Boolean) {
        worker.execute {
            runCatching { db.runInTransaction {
                if (confirm) ChatWeightPipeline(db).confirmCandidate(id)
                else ChatWeightPipeline(db).rejectCandidate(id)
            } }
            runOnUiThread { if (!isFinishing && !isDestroyed) refresh() }
        }
    }
}
