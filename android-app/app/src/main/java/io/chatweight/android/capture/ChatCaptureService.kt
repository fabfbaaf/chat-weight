package io.chatweight.android.capture

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.graphics.Rect
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import io.chatweight.android.capture.ocr.MlKitOcr
import io.chatweight.android.capture.ocr.OcrLine
import io.chatweight.android.capture.ocr.ScreenCapture
import io.chatweight.android.core.BubbleRect
import io.chatweight.android.core.ChatSnapshot
import io.chatweight.android.core.Msg
import io.chatweight.android.core.Prefs
import io.chatweight.android.core.kb.KbStore
import io.chatweight.android.ingest.CapturedLine
import io.chatweight.android.ingest.LocalSummary
import io.chatweight.android.ingest.MessageIngestService
import io.chatweight.android.ingest.MessageFingerprint
import io.chatweight.android.overlay.OverlayController
import io.chatweight.android.reply.ReplyAssistant
import io.chatweight.core.Platform
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.Future

/**
 * The live capture service (registered under a disguised class name so WeChat
 * exposes its node tree — see the disguised subclass). It reads whichever
 * adapted chat app is in the foreground, detects a new incoming message from the
 * other person, runs Jev analysis off the main thread, and drives the floating
 * overlay.
 *
 * Per-app node rules live in [ChatAppAdapter] implementations; everything here
 * is app-agnostic.
 *
 * It never sends a message. The only write action is ACTION_SET_TEXT (or a
 * clipboard PASTE fallback) to fill the chat input box when the user taps
 * "填入"; the user still presses send.
 */
open class ChatCaptureService : AccessibilityService() {

    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newFixedThreadPool(2)

    /** Compatibility behavior inherited from upstream Jev. Do not rename the
     * special AccessibilityService class without real-device verification. */
    private val adapters = listOf(QQAdapter(), WeChatAdapter()).associateBy { it.pkg }

    /** Submit to the worker, ignoring rejection after the service is torn down
     *  (a stale overlay callback must never crash the process). */
    private fun submit(task: () -> Unit) {
        try { worker.execute(task) } catch (_: RejectedExecutionException) { }
    }
    private lateinit var prefs: Prefs
    private var overlay: OverlayController? = null

    private var lastSignature: String = ""
    private var activePkg: String? = null
    private var analyzing = false
    private var analysisGeneration = 0L
    private var analysisJob: Future<*>? = null
    private var latestSummary: LocalSummary? = null
    private val ingest by lazy { MessageIngestService(applicationContext) }

    private var pendingSnapshot: ChatSnapshot? = null
    @Volatile private var currentSnapshot: ChatSnapshot? = null
    private var foregroundPkg: String? = null

    // ---- OCR path (B stage). Everything here runs on the main thread: the
    // screenshot callback and the ML Kit callback are both posted back to it.
    private val screenCapture by lazy {
        ScreenCapture(this,
            hideOverlay = { overlay?.setHiddenForShot(true) },
            restoreOverlay = { overlay?.setHiddenForShot(false) })
    }
    private val ocr = MlKitOcr()
    private var ocrBusy = false

    /** What the screen looked like the last time we fired an automatic shot.
     *  See [ocrSignature]: this is the brake on the OCR path. */
    private var lastOcrSignature: String = ""
    private var lastOcrAttemptAt = 0L
    private var eventCaptureScheduled = false
    private var lastEventCaptureAt = 0L
    private val eventCapture = Runnable {
        eventCaptureScheduled = false
        lastEventCaptureAt = SystemClock.elapsedRealtime()
        maybeCapture()
    }

    private fun scheduleEventCapture() {
        if (eventCaptureScheduled) return
        val sinceLast = SystemClock.elapsedRealtime() - lastEventCaptureAt
        eventCaptureScheduled = true
        main.postDelayed(eventCapture, (EVENT_CAPTURE_MIN_INTERVAL_MS - sinceLast).coerceAtLeast(0L))
    }
    private var wechatPollScheduled = false
    private val wechatPoll = object : Runnable {
        override fun run() {
            wechatPollScheduled = false
            if (!::prefs.isInitialized || !prefs.enabled || !prefs.wechatCaptureEnabled) return
            val pkg = rootInActiveWindow?.packageName?.toString()
            if (pkg != PKG_WECHAT && !(pkg == null && foregroundPkg == PKG_WECHAT)) return
            maybeCapture()
            scheduleWeChatPoll()
        }
    }

    private fun scheduleWeChatPoll() {
        if (wechatPollScheduled) return
        wechatPollScheduled = true
        main.postDelayed(wechatPoll, WECHAT_POLL_MS)
    }

    private fun stopWeChatPoll() {
        main.removeCallbacks(wechatPoll)
        wechatPollScheduled = false
    }

    /** Avoid repeating the opt-out notice while WeChat remains foreground. */
    private var wechatNoticeShown = false

    override fun onServiceConnected() {
        super.onServiceConnected()
        isConnected = true
        prefs = Prefs(this)
        overlay = OverlayController(this)
        overlay?.onManualAnalyze = {
            currentSnapshot?.let { pendingSnapshot = it; runAnalysis(manual = true) }
        }
        // Bubble menu: file the open conversation as a knowledge-base contact.
        // Contacts are never created automatically — this is the one-tap way in.
        overlay?.onSaveContact = {
            val title = currentSnapshot?.title
            val pkg = activePkg ?: foregroundPkg ?: ""
            when {
                title.isNullOrBlank() -> overlay?.toast("当前会话没有标题，存不了")
                isTransientTitle(title) -> overlay?.toast("当前会话标题还没加载出来，稍后再试")
                else -> submit {
                    val msg = try {
                        KbStore.get(this).saveOrMergeContact(title, pkg)
                    } catch (e: Exception) { "保存失败：${e.javaClass.simpleName}" }
                    main.post { overlay?.toast(msg) }
                }
            }
        }
        // Bubble menu: one manual screenshot + OCR, for any app at all.
        overlay?.onOcrCapture = { ocrCaptureManual() }
        // Keep the process at foreground importance so MIUI does not freeze us.
        if (prefs.enabled) runCatching { KeepAliveService.start(this) }
        // Load the bundled OCR model now, off the main thread: the first
        // recognize() otherwise pays for it inside the screenshot callback.
        submit { MlKitOcr.warmUp() }
        // HyperOS may kill and restart us. On (re)connect, proactively re-show the
        // bubble for whatever chat is already open, so it comes back on its own
        // instead of waiting for the user to scroll.
        main.postDelayed({ if (prefs.enabled) runCatching { maybeCapture() } }, 900)
        Log.i(TAG, "capture service connected")
        for (pkg in adapters.keys) {
            val version = runCatching { packageManager.getPackageInfo(pkg, 0).versionName }.getOrNull()
            Log.i(TAG, "capture target=$pkg version=${version ?: "not installed"}")
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        if (!prefs.enabled) { main.post { overlay?.hide() }; return }

        val active = rootInActiveWindow?.packageName?.toString()
        if (active == PKG_WECHAT || active == null && event.packageName?.toString() == PKG_WECHAT) {
            foregroundPkg = PKG_WECHAT
            if (prefs.wechatCaptureEnabled) {
                WeChatCaptureStatus.markEvent(this)
                scheduleWeChatPoll()
            }
        } else if (active != null && active != PKG_WECHAT) {
            foregroundPkg = active
            stopWeChatPoll()
        }

        val type = event.eventType
        // Decide "did we leave the chat app" from the REAL active window, not the
        // event's package. The event package can be an IME (e.g. com.tencent.wetype)
        // or the status bar while the chat app is still foreground — keying off it
        // made the bubble flicker (hide → re-show → hide…). rootInActiveWindow stays
        // on the chat app while the keyboard is up, so this is stable.
        //
        // An app with no adapter is NOT a reason to take the bubble away: the only
        // way into DingTalk / Telegram / anything else is the bubble menu's
        // "截屏识别一次", and a bubble that is gone cannot be tapped. So we park
        // the idle bubble there instead — still no automatic capture, no analysis.
        // The bubble does come off for places where it would only be in the way:
        // our own settings screens, the launcher, and the system UI.
        if (type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            val fg = rootInActiveWindow?.packageName?.toString()
            // Respect the user's WeChat capture switch before reading its window.
            if (fg == PKG_WECHAT && !prefs.wechatCaptureEnabled) { foregroundPkg = fg; showWeChatDisabled(auto = true); return }
            if (fg != null && fg !in adapters) {
                foregroundPkg = fg
                wechatNoticeShown = false // left WeChat → allow the notice again next visit
                val drop = fg == packageName ||
                    fg.contains("launcher", ignoreCase = true) ||
                    fg == "com.miui.home" ||
                    fg == "com.android.systemui"
                main.post { if (drop) overlay?.hide() else overlay?.showIdle(null) }
                return
            }
        }

        when (type) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED,
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED,
            AccessibilityEvent.TYPE_VIEW_SCROLLED -> scheduleEventCapture()
        }
    }

    private fun maybeCapture() {
        val root = rootInActiveWindow ?: run {
            if (foregroundPkg == PKG_WECHAT) WeChatCaptureStatus.mark(this, "微信窗口节点暂不可用")
            return
        }
        val pkg = root.packageName?.toString()
        // The opt-out is checked before either Accessibility parsing or OCR.
        if (pkg == PKG_WECHAT && !prefs.wechatCaptureEnabled) { showWeChatDisabled(auto = true); return }
        if (pkg == PKG_WECHAT) scheduleWeChatPoll()
        if (pkg == "com.tencent.mobileqq" && !prefs.qqCaptureEnabled) {
            overlay?.hide(); return
        }
        wechatNoticeShown = false // any other foreground → allow the notice again next WeChat visit
        // Apps with no adapter are never handled automatically (v1.3 revision):
        // the only way in for them is the bubble menu's "截屏识别一次".
        val adapter = adapters[pkg] ?: return
        // Outside a chat window (the conversation list, a profile, settings…) the
        // adapter returns null. That is NOT a reason to show nothing: an adapted
        // app must behave at least as well as an unadapted one, which parks an idle
        // bubble so the menu stays reachable. Without this, opening QQ / Feishu on
        // their list screen produced no bubble at all.
        val rawSnapshot = adapter.extract(root, resources)
        if (pkg == PKG_WECHAT && rawSnapshot != null) Log.i(TAG,
            "wechat tree bubbles=${rawSnapshot.bubbleRects.size} readable=${rawSnapshot.messages.size} " +
                "title=${!rawSnapshot.title.isNullOrBlank()} firstTop=${rawSnapshot.bubbleRects.firstOrNull()?.rect?.top ?: -1}")
        if (rawSnapshot == null) {
            if (pkg == PKG_WECHAT) WeChatCaptureStatus.mark(this,
                if (root.childCount == 0) "微信窗口节点树为空；系统或微信可能限制了读取"
                else "未找到聊天气泡节点；可能不在聊天页或版本不兼容")
            if (overlay?.isShowing() != true) main.post { overlay?.showIdle(null) }
            return
        }
        // Stabilize the title BEFORE anything below reads it: some apps (X) show
        // a transient "连接中…" title for a moment right after opening a thread.
        val snapshot = stabilizeTitle(rawSnapshot)
        if (snapshot.title.isNullOrBlank() && snapshot.messages.isNotEmpty()) {
            if (pkg == PKG_WECHAT && prefs.ocrFallback && snapshot.bubbleRects.isNotEmpty()) {
                WeChatCaptureStatus.mark(this, "气泡可读，标题缺失；尝试 OCR 标题")
                val sig = ocrSignature(pkg, null, snapshot.bubbleRects)
                val now = SystemClock.elapsedRealtime()
                if (!ocrBusy && OcrRefreshPolicy.shouldCapture(sig, lastOcrSignature, now, lastOcrAttemptAt)) {
                    lastOcrSignature = sig
                    lastOcrAttemptAt = now
                    ocrCapture(null, snapshot.bubbleRects, pkg, manual = false)
                }
            } else if (pkg == PKG_WECHAT) WeChatCaptureStatus.mark(this, "气泡可读，但未识别会话标题")
            if (overlay?.isShowing() != true) main.post { overlay?.showIdle(null) }
            return
        }
        if (!prefs.isAllowed(snapshot.title)) { main.post { overlay?.hide() }; return }
        // In a chat window but the tree holds no text (Feishu draws its bodies,
        // WeChat hides them when the disguise fails) → screenshot + OCR, subject
        // to ScreenCapture's own >=1s throttle and failure backoff.
        if (snapshot.messages.isEmpty()) {
            // In a chat window, but the tree carries no text (Feishu draws its
            // message bodies). Park the bubble BEFORE attempting OCR, so the user
            // still has something to tap when OCR is off, deduped, or comes back
            // empty — previously all three cases left the screen with no bubble.
            if (overlay?.isShowing() != true) main.post { overlay?.showIdle(snapshot.title) }
            if (prefs.ocrFallback) {
                // Gate BEFORE the shot, not after the OCR. Feishu's tree is empty
                // on every content-changed event, and a successful shot resets the
                // failure backoff — so without this the caret blinking or an
                // "online" badge flipping keeps a screenshot going out every
                // second forever. The picture can only differ if the bubbles moved
                // or the conversation changed, and that is exactly what the
                // signature measures.
                val sig = ocrSignature(pkg ?: "", snapshot.title, snapshot.bubbleRects)
                val now = SystemClock.elapsedRealtime()
                if (!OcrRefreshPolicy.shouldCapture(sig, lastOcrSignature, now, lastOcrAttemptAt)) return
                if (ocrBusy) return
                lastOcrSignature = sig
                lastOcrAttemptAt = now
                ocrCapture(snapshot.title, snapshot.bubbleRects, pkg ?: "", manual = false)
            }
            return
        }

        // Switching to another adapted app resets the dedupe signature, so two apps
        // whose last few messages happen to match cannot swallow each other.
        if (pkg != activePkg) { activePkg = pkg; lastSignature = "" }

        currentSnapshot = snapshot
        val sig = "${pkg}:${snapshot.title}:${snapshot.signature()}"
        val showing = overlay?.isShowing() == true
        // Same content and the bubble is already up → nothing to do.
        if (sig == lastSignature && showing) return
        // Same content but the bubble is gone (killed by MIUI, or we left and came
        // back) → just put the bubble back, do NOT re-analyze (saves tokens/time).
        if (sig == lastSignature && !showing) { main.post { overlay?.showIdle(snapshot.title) }; return }
        // Anything else reaching here is a genuinely different conversation (new
        // app, or new content in this one) — a leftover judgment/candidates from
        // whatever was shown before must not leak into it.
        main.post { overlay?.resetForNewConversation() }
        lastSignature = sig
        analysisGeneration++
        analysisJob?.cancel(true)
        analyzing = false
        latestSummary = null
        Log.d(TAG, "snapshot[$pkg] conversation=${MessageFingerprint.sha256(snapshot.title.orEmpty()).take(8)} n=${snapshot.messages.size} " +
            snapshot.messages.takeLast(6).joinToString(" | ") { "${it.side}:${it.text.length}" }) // sides + lengths only, never content
        if (pkg == PKG_WECHAT) WeChatCaptureStatus.mark(this, "读到 ${snapshot.messages.size} 条可见气泡，正在入库")

        // Both sides enter local analysis. The optional network branch starts only
        // after MessageIngestService commits the Room transaction.
        ingestCapture(snapshot, pkg ?: "", "android_accessibility")
    }

    /**
     * Explain that WeChat capture is switched off. Automatic events show the
     * notice once per visit; a manual bubble tap can show it again.
     */
    private fun showWeChatDisabled(auto: Boolean) {
        if (auto && wechatNoticeShown) return
        wechatNoticeShown = true
        // No popup panel in WeChat — a full card is intrusive when others can see
        // the screen. Take the overlay off WeChat entirely and show the reason
        // once as a small transient toast.
        main.post { overlay?.hide(); overlay?.toast(WECHAT_DISABLED_MSG) }
    }

    /** A placeholder title an app shows only for a moment (e.g. X's "连接中…"
     *  right after opening a DM thread) — never a real conversation title.
     *  Blank/null counts too, so a caller can always fall back the same way. */
    private fun isTransientTitle(t: String?): Boolean {
        val trimmed = t?.trim()?.removeSuffix("…")?.removeSuffix("...")?.trim()
        if (trimmed.isNullOrEmpty()) return true
        val lower = trimmed.lowercase()
        return TRANSIENT_TITLE_WORDS.any { lower.contains(it.lowercase()) }
    }

    /** Never borrow another conversation's title during a transient screen. */
    private fun stabilizeTitle(snapshot: ChatSnapshot): ChatSnapshot =
        if (isTransientTitle(snapshot.title)) snapshot.copy(title = null) else snapshot

    private fun ingestCapture(snapshot: ChatSnapshot, pkg: String, source: String, manual: Boolean = false) {
        val platform = when (pkg) {
            "com.tencent.mobileqq" -> Platform.QQ
            PKG_WECHAT -> Platform.WECHAT
            else -> return
        }
        val token = analysisGeneration
        val lines = snapshot.messages.map { CapturedLine(it.side, it.text, it.senderName) }
        ingest.enqueue(platform, snapshot.title, lines, source) { outcome ->
            if (pkg == PKG_WECHAT) WeChatCaptureStatus.mark(this,
                when {
                    outcome.error != null -> "消息入库失败：${outcome.error}"
                    outcome.inserted > 0 -> "新消息已入库：${outcome.inserted} 条"
                    else -> "当前屏幕无新增消息"
                }, inserted = outcome.inserted > 0)
            main.post {
                if (token != analysisGeneration) return@post
                latestSummary = outcome.summary
                if (outcome.error != null) {
                    overlay?.showError("本地入库失败：${outcome.error}")
                    return@post
                }
                pendingSnapshot = snapshot
                outcome.summary?.let { summary ->
                    overlay?.setNote("${summary.displayName} · ${summary.relationshipType.uppercase()} · 我 ${summary.selfEngagement.toInt()} / 对方 ${summary.otherEngagement.toInt()} · Stage ${summary.expressionStage}")
                }
                if ((manual || outcome.inserted > 0 && snapshot.latestFrom == "other" && prefs.autoAnalyze) &&
                    prefs.aiReplyEnabled && prefs.hasKey()
                ) runAnalysis(manual = manual)
                else overlay?.showIdle(snapshot.title)
            }
        }
    }

    private fun runAnalysis(manual: Boolean = false) {
        val snapshot = pendingSnapshot ?: return
        if (analyzing) return
        if (!prefs.aiReplyEnabled) { if (manual) overlay?.showError("AI 回复已关闭，本地关系分析仍在运行"); return }
        if (!prefs.hasKey()) { if (manual) overlay?.showError("未设置判断接口密钥，去设置里填"); return }
        val token = analysisGeneration
        analyzing = true
        main.post {
            overlay?.showLoading()
            snapshot.note?.let { overlay?.setNote(it) }
        }
        try {
            analysisJob = worker.submit {
                val result = ReplyAssistant(prefs).analyze(snapshot, latestSummary, manual)
                main.post {
                    if (token != analysisGeneration) return@post
                    analyzing = false
                    if (result.judgment?.error != null) overlay?.showError("判断接口暂不可用")
                    else {
                        result.judgment?.let { overlay?.showJudgment(it) }
                        overlay?.showReplies(result.candidates, result.reason) { text -> fillInput(text) }
                    }
                }
            }
        } catch (_: RejectedExecutionException) { analyzing = false }
    }

    // ------------------------------------------------------------------ OCR

    /**
     * Bubble menu → "截屏识别一次". Works on ANY app, adapted or not: one whole
     * screen shot, every line OCR'd, lines grouped into pseudo-bubbles by line
     * spacing. Nobody can tell who said what this way, so everything is filed as
     * the other person and the panel says so.
     */
    private fun ocrCaptureManual() {
        val root = rootInActiveWindow
        val pkg = root?.packageName?.toString() ?: foregroundPkg ?: activePkg ?: ""
        if (pkg == PKG_WECHAT && !prefs.wechatCaptureEnabled) { showWeChatDisabled(auto = false); return }
        if (pkg == "com.tencent.mobileqq" && !prefs.qqCaptureEnabled) return
        val adapted = root?.let { adapters[pkg]?.extract(it, resources) }
        val title = adapted?.title ?: root?.let {
            findTitleInActionBar(it, Int.MAX_VALUE, resources.displayMetrics.widthPixels, resources, 0.15, 0.85)
        }
        ocrCapture(title, adapted?.bubbleRects ?: emptyList(), pkg, manual = true)
    }

    /**
     * What the screen would look like to a camera, as far as the tree can tell.
     *
     * Feishu: the conversation title plus every bubble rectangle and its side —
     * the bubbles move whenever the list scrolls or a message arrives, and stay
     * put when only chrome (caret, presence dot, timestamp) redraws. Apps that
     * give us no rectangles fall back to package + title, which at least stops a
     * burst of events on one screen from becoming a burst of screenshots.
     */
    private fun ocrSignature(pkg: String, title: String?, rects: List<BubbleRect>): String {
        if (rects.isEmpty()) return pkg + "|" + (title ?: "")
        return (title ?: "") + "|" + rects.joinToString(";") { br ->
            val r = br.rect
            "${r.left},${r.top},${r.right},${r.bottom},${br.side}"
        }
    }

    /**
     * Screenshot, then either OCR each known bubble rect (Feishu: the tree knows
     * where the bubbles are and who sent them, just not what they say) or OCR
     * the whole screen (everything else).
     */
    private fun ocrCapture(treeTitle: String?, rects: List<BubbleRect>, pkg: String, manual: Boolean) {
        if (ocrBusy) return
        ocrBusy = true
        screenCapture.capture { res ->
            when (res) {
                is ScreenCapture.Result.Failed -> {
                    ocrBusy = false
                    Log.i(TAG, "ocr: screenshot failed code=${res.code}")
                    if (pkg == PKG_WECHAT) WeChatCaptureStatus.mark(this, "OCR 截屏失败：${res.code}")
                    // Nothing was read, so the signature must not claim this
                    // screen is done — the next event may retry, still held
                    // back by ScreenCapture's own throttle and failure backoff.
                    if (!manual) lastOcrSignature = ""
                    // Throttle/interval codes are transient timing, not
                    // something the user can act on — nagging would be constant.
                    val transient = res.code == ScreenCapture.CODE_THROTTLED || res.code == 3
                    if (manual || !transient) overlay?.showError(res.humanMessage)
                }
                is ScreenCapture.Result.Ok -> {
                    if (rootInActiveWindow?.packageName?.toString() != pkg) {
                        runCatching { res.bitmap.recycle() }
                        ocrBusy = false
                        return@capture
                    }
                    if (pkg == PKG_WECHAT) WeChatCaptureStatus.mark(this, "截屏成功，正在本机 OCR")
                    ocr.scaleX = res.scaleX; ocr.scaleY = res.scaleY
                    ocr.originX = res.originX; ocr.originY = res.originY
                    if (rects.isNotEmpty()) {
                        // Re-measure inside the callback. The rects handed in were
                        // read before the 120ms overlay-hide wait and the shot
                        // itself; one scroll tick in between and we would crop the
                        // rows next to the ones in the picture. Fall back to the
                        // old rects only if the tree gives us nothing now.
                        val fresh = rootInActiveWindow?.let { adapters[pkg]?.extract(it, resources)?.bubbleRects }
                        ocrByRects(res.bitmap, if (fresh.isNullOrEmpty()) rects else fresh, treeTitle, pkg, manual)
                    } else ocrWholeScreen(res.bitmap, treeTitle, pkg, manual)
                }
            }
        }
    }

    /** One OCR pass per bubble rectangle; each rect becomes exactly one message. */
    private fun ocrByRects(bmp: Bitmap, rects: List<BubbleRect>, title: String?, pkg: String, manual: Boolean) {
        if (pkg == PKG_WECHAT && title.isNullOrBlank()) {
            val header = Rect(0, 0, bmp.width, (bmp.height * 0.19f).toInt())
            ocr.recognize(bmp, header) { lines ->
                val resolved = WeChatTitleOcr.pick(lines, resources.displayMetrics.widthPixels,
                    rects.minOf { it.rect.top })
                Log.i(TAG, "wechat title OCR lines=${lines.size} candidate=${resolved != null} " +
                    "firstBubbleTop=${rects.minOf { it.rect.top }}")
                if (resolved == null) WeChatCaptureStatus.mark(this, "OCR 未识别到会话标题")
                ocrBubbleRegions(bmp, rects, resolved, pkg, manual)
            }
        } else ocrBubbleRegions(bmp, rects, title, pkg, manual)
    }

    private fun ocrBubbleRegions(bmp: Bitmap, rects: List<BubbleRect>, title: String?, pkg: String, manual: Boolean) {
        val sx = ocr.scaleX; val sy = ocr.scaleY
        // Screen -> bitmap: drop the window origin first. A window shot does not
        // start at (0,0) in split screen or when it excludes the status bar.
        val ox = ocr.originX; val oy = ocr.originY
        val out = arrayOfNulls<Msg>(rects.size)
        var remaining = rects.size
        rects.forEachIndexed { i, br ->
            val region = Rect(
                ((br.rect.left - ox) * sx).toInt(), ((br.rect.top - oy) * sy).toInt(),
                ((br.rect.right - ox) * sx).toInt(), ((br.rect.bottom - oy) * sy).toInt())
            ocr.recognize(bmp, region) { lines ->
                val text = cleanBubbleText(lines.joinToString(" ") { it.text })
                if (text.isNotEmpty()) out[i] = Msg(br.side, text)
                remaining--
                if (remaining == 0) {
                    runCatching { bmp.recycle() }
                    finishOcrSnapshot(ChatSnapshot(title, out.filterNotNull()), pkg, manual)
                }
            }
        }
    }

    /** Whole screen minus the top bar and the input area, grouped by line gaps. */
    private fun ocrWholeScreen(bmp: Bitmap, treeTitle: String?, pkg: String, manual: Boolean) {
        val region = Rect(0, (bmp.height * TOP_CROP).toInt(), bmp.width, (bmp.height * BOTTOM_CROP).toInt())
        ocr.recognize(bmp, region) { lines ->
            runCatching { bmp.recycle() }
            val msgs = groupOcrLines(lines)
            val title = treeTitle?.takeIf { it.isNotBlank() }
                ?: lines.firstOrNull()?.text?.trim()?.take(24)
            finishOcrSnapshot(ChatSnapshot(title, msgs, note = OCR_NOTE), pkg, manual)
        }
    }

    /**
     * OCR lines → "bubbles": a gap larger than 1.2x the previous line's height
     * starts a new one. Side is unknowable from a flat screen read, so every
     * group is filed as the other person (and [OCR_NOTE] says so on the panel).
     */
    private fun groupOcrLines(lines: List<OcrLine>): List<Msg> {
        val usable = lines
            .filter { it.text.isNotBlank() && !PURE_TIME.matches(it.text.trim()) }
            .sortedBy { it.bounds.top }
        val out = ArrayList<Msg>()
        val buf = StringBuilder()
        var prev: OcrLine? = null
        for (l in usable) {
            val p = prev
            if (p != null) {
                val gap = l.bounds.top - p.bounds.bottom
                val lineHeight = maxOf(p.bounds.height(), 1)
                if (gap > lineHeight * 1.2f) {
                    if (buf.isNotEmpty()) { out.add(Msg("unknown", buf.toString())); buf.setLength(0) }
                }
            }
            if (buf.isNotEmpty()) buf.append(' ')
            buf.append(l.text.trim())
            prev = l
        }
        if (buf.isNotEmpty()) out.add(Msg("unknown", buf.toString()))
        return out
    }

    /** Strip the read receipt and the timestamp Feishu glues onto a bubble. */
    private fun cleanBubbleText(raw: String): String {
        var t = raw.trim()
        var changed = true
        while (changed && t.isNotEmpty()) {
            changed = false
            for (tail in arrayOf("已读", "未读")) {
                if (t.endsWith(tail)) { t = t.removeSuffix(tail).trim(); changed = true }
            }
            TAIL_TIME.find(t)?.let { t = t.substring(0, it.range.first).trim(); changed = true }
        }
        return t
    }

    /** Shared tail of both OCR paths: dedupe, then analyze or park the bubble. */
    private fun finishOcrSnapshot(snapshot: ChatSnapshot, pkg: String, manual: Boolean) {
        ocrBusy = false
        if (rootInActiveWindow?.packageName?.toString() != pkg) return
        // Counts only — OCR'd chat text never goes to logcat.
        val hasKnownSide = snapshot.messages.any { it.side == "me" || it.side == "other" }
        Log.i(TAG, "ocr[$pkg] msgs=${snapshot.messages.size} title=${!snapshot.title.isNullOrBlank()} " +
            "knownSide=$hasKnownSide manual=$manual")
        if (snapshot.messages.isEmpty()) {
            if (pkg == PKG_WECHAT) WeChatCaptureStatus.mark(this, "OCR 未识别出气泡文字")
            if (manual) overlay?.showError("这一屏没认出文字")
            return
        }
        if (snapshot.title.isNullOrBlank() && pkg in adapters) {
            if (pkg == PKG_WECHAT) WeChatCaptureStatus.mark(this, "已读到气泡，但会话标题仍不可用")
            overlay?.showError("未识别出当前会话标题，请重新打开会话后再试")
            return
        }
        if (!prefs.isAllowed(snapshot.title)) { overlay?.hide(); return }

        if (pkg.isNotEmpty() && pkg != activePkg) { activePkg = pkg; lastSignature = "" }
        currentSnapshot = snapshot
        val sig = snapshot.signature()
        // Manual taps always re-run; the automatic path dedupes like the tree path.
        if (!manual && sig == lastSignature) {
            if (overlay?.isShowing() != true) overlay?.showIdle(snapshot.title)
            return
        }
        // Same rule as the tree path: past this point the conversation is either
        // new or being force-refreshed, so drop whatever was shown before.
        overlay?.resetForNewConversation()
        lastSignature = sig
        analysisGeneration++
        analysisJob?.cancel(true)
        analyzing = false
        latestSummary = null
        pendingSnapshot = snapshot
        // A flat OCR pass cannot identify the speaker. Never score it as an
        // incoming message; known-side bubble OCR can enter the local pipeline.
        if (snapshot.messages.any { it.side == "me" || it.side == "other" }) {
            ingestCapture(snapshot, pkg, "android_ocr", manual)
        } else {
            overlay?.setNote(OCR_NOTE)
            overlay?.showIdle(snapshot.title)
        }
    }

    /** Fill the chat input box with the chosen reply (never sends). */
    private fun fillInput(text: String) {
        submit {
            // Fast path: SET_TEXT works when the box already has input focus and no
            // IME composing session is active.
            var ok = trySetText(text)
            if (!ok) {
                // Otherwise focus the box (pops the keyboard) and retry SET_TEXT;
                // if the IME composing region still swallows it (WeChat), PASTE from
                // the clipboard. The box is cleared before PASTE so a SET_TEXT that
                // silently took (but failed verification) never gets doubled.
                // Never clicks send.
                val edit = rootInActiveWindow?.let { findEditable(it) }
                if (edit != null) {
                    edit.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    Thread.sleep(300)
                    ok = trySetText(text)
                    if (!ok) {
                        copyToClipboard(text)
                        val focused = rootInActiveWindow?.let { findEditable(it) } ?: edit
                        setTextRaw(focused, "")
                        val pasted = focused.performAction(AccessibilityNodeInfo.ACTION_PASTE)
                        Thread.sleep(150)
                        val after = readInput()
                        ok = (after != null && after.contains(text)) || (pasted && after == null)
                        Log.i(TAG, "fill: paste=$pasted readback=${after?.length ?: -1}")
                    }
                }
            }
            main.post {
                if (ok) overlay?.toast("已填入，确认后自己发送")
                else { copyToClipboard(text); overlay?.toast("已复制，长按输入框粘贴") }
            }
        }
    }

    /** Set text on the chat input box, verifying it actually took. */
    private fun trySetText(text: String): Boolean {
        val edit = rootInActiveWindow?.let { findEditable(it) } ?: return false
        if (!setTextRaw(edit, text)) return false
        // SET_TEXT can report success without filling an unfocused box; verify.
        // Read back through refresh() — the node cache can still hold the old
        // (empty) text right after the action, which made Feishu look like a
        // failure and triggered a second PASTE on top.
        Thread.sleep(150)
        val after = readInput()
        Log.i(TAG, "fill: setText readback=${after?.length ?: -1} want=${text.length}")
        return after == text
    }

    private fun setTextRaw(edit: AccessibilityNodeInfo, text: String): Boolean {
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return edit.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    /** Current text of the input box, fetched fresh (bypassing the node cache). */
    private fun readInput(): String? {
        val edit = rootInActiveWindow?.let { findEditable(it) } ?: return null
        runCatching { edit.refresh() }
        return edit.text?.toString()
    }

    private fun findEditable(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val stack = ArrayDeque<AccessibilityNodeInfo>()
        stack.addLast(root)
        var guard = 0
        while (stack.isNotEmpty() && guard < 5000) {
            guard++
            val node = stack.removeLast()
            if (node.isEditable) return node
            for (i in node.childCount - 1 downTo 0) node.getChild(i)?.let { stack.addLast(it) }
        }
        return null
    }

    private fun copyToClipboard(text: String) {
        val cm = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
        cm.setPrimaryClip(android.content.ClipData.newPlainText("jev_reply", text))
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        main.removeCallbacks(eventCapture)
        eventCaptureScheduled = false
        super.onDestroy()
        stopWeChatPoll()
        isConnected = false
        // Tear the overlay down and cut its callback so a stale button tap can
        // never call back into this dead instance.
        overlay?.onManualAnalyze = null
        overlay?.onSaveContact = null
        overlay?.onOcrCapture = null
        overlay?.hide()
        overlay = null
        analysisJob?.cancel(true)
        if (::prefs.isInitialized) ingest.shutdown()
        worker.shutdownNow()
    }

    companion object {
        @Volatile var isConnected: Boolean = false
            private set
        private const val TAG = "JEVASSIST"

        /** WeChat's package. Reading it (node tree / screenshot / OCR) is what
         *  trips WeChat's anti-screenshot risk control, so it is fully disabled:
         *  no adapter, no capture, only a one-time "not supported" notice. */
        private const val PKG_WECHAT = "com.tencent.mm"
        private const val WECHAT_POLL_MS = 4_000L
        private const val EVENT_CAPTURE_MIN_INTERVAL_MS = 600L

        /** Shown once when the foreground is WeChat. Plain words, full-width
         *  punctuation; steers the user to a still-supported app. */
        private const val WECHAT_DISABLED_MSG =
            "微信采集默认关闭，可在 ChatWeight 首页手动开启（兼容性待真机验证）"

        /** Whole-screen OCR keeps the middle: no action bar, no input area. */
        private const val TOP_CROP = 0.12f
        private const val BOTTOM_CROP = 0.84f

        /** Said on the panel whenever a snapshot came from flat-screen OCR. */
        private const val OCR_NOTE = "OCR 未能判断发送方，这屏不会计入关系分析"

        private val PURE_TIME = Regex("""\d{1,2}[:：]\d{2}""")
        private val TAIL_TIME = Regex("""\d{1,2}[:：]\d{2}$""")

        /** Transient placeholder titles apps show while a chat page is still
         *  connecting/loading — see [isTransientTitle]. Matched as a substring,
         *  case-insensitive, after trimming a trailing ellipsis. */
        private val TRANSIENT_TITLE_WORDS = listOf(
            "连接中", "正在连接", "未连接", "Connecting",
            "加载中", "Loading", "同步中", "Syncing"
        )
    }
}
