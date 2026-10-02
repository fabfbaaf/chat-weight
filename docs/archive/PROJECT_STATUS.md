# Project Status — V0.2.0

## 已完成

### 核心
- `UnifiedMessage` 跨平台模型
- Session 30分钟切分基础实现
- WeightEventType / WeightRuleRegistry
- 本地 WeightEngine：重复衰减、每日上限、Recent/Base 双层衰减
- RelationshipType / RelationshipEventType
- RelationshipEngine：表达 Raw、14天 Heat 半衰期、Stage Gate、最高历史 Stage
- RelationshipEventDetector：本地行为、关心短语、想念表达、特殊称呼、明确表白候选、仅朋友、关系确认候选、关系结束候选
- 关键关系状态人工确认政策
- SQLite 全量 schema
- Python 参考实现 + Demo
- Kotlin 纯核心实现

### Windows 微信采集 V0.2
- Jev Windows 风格 `Windows Graphics Capture` 接入
- 像素锚点聊天区定位
- RapidOCR 本地 OCR
- 气泡颜色 `me / her / gray / image` 分类
- 群聊 OCR 发言人名提取
- 每会话 Reader 滚动去重
- 首帧预热：默认不重复写入当前屏幕旧消息
- OCR 批次标准化为 `UnifiedMessage`
- 私聊 `unknown -> private` 自动识别及历史 NULL person 回填
- 群聊 group-scoped 成员 ID，避免同名跨群误合并
- `messages` + `chat_sessions` 实时写 SQLite
- SQLite WAL 模式
- Windows 一键依赖安装 / 启动 / 最近消息查看脚本
- 上游 Jev MIT LICENSE / NOTICE 保留

## 验证

- Python unit tests: 10/10 passed
- Python compileall: passed
- SQLite schema load: passed
- Kotlin core compile/test: existing verification path retained

说明：当前构建环境不是 Windows，因此 WGC 无法在这里连接真实微信窗口做端到端真机测试；WGC/OCR 路径按当前 jev-chat-windows 源码结构接入，并把可在非 Windows 环境验证的标准化、数据库、私聊/群聊映射和去重边界全部做了单测。

## 下一轮

- Windows 真机日志反馈后调 OCR / area 参数
- Android QQ Accessibility 实际代码接入
- 图片 / 表情 / 语音 / 文件消息类型检测
- WeightEventDetector 的 Burst / 短回复链 / 问句24小时未回复定时结算
- `REMEMBER_AND_FOLLOW_UP` 历史语义检索
- 可选大模型 SemanticEventDetector
- UI：联系人列表、关系详情、时间线、Review Center
- 微信/QQ 联系人跨平台人工合并界面

## V0.3.0 realtime analysis closure

Windows WeChat ingestion is now wired through the persisted analysis pipeline:

- UnifiedMessage -> persisted/restored SessionManager
- WeightEventDetector -> WeightEngine -> weight_events / weight_state
- Burst, follow-up, short-reply-chain, turn/duration milestones
- Daily active/streak frequency events with idempotent settlement
- RelationshipEventDetector -> relationship_event_candidates review queue
- AUTO/HIGH_CONFIDENCE events -> RelationshipEngine for CRUSH/PARTNER profiles
- USER_REVIEW / MANUAL_ONLY events never change expression stage until explicitly confirmed
- daily_metrics, daily_weight_snapshots, relationship_daily_snapshot are updated incrementally
- relationship type and review queue can be managed locally with `manage.cmd`
- restart within the 30-minute session gap restores the previous session from SQLite, avoiding duplicate SESSION_START scoring

Verification: 15 Python tests pass; SQLite schema loads; Kotlin core compiles/tests pass.
The remaining Windows work is real-device compatibility validation of WGC/RapidOCR against the user's WeChat build, DPI/theme/window layout.

## V0.4.0 Android integration

- Android 11+ app restored from Jev Android source, with ChatWeight package and branding.
- QQ and opt-in WeChat adapters feed a per-conversation `UnifiedMessage` normalizer and Room.
- Shared `core-kotlin` algorithms drive persisted session, weight, relationship review and daily snapshots.
- AI Reply is optional; the local pipeline runs without keys or network. The overlay fills a selected reply and never sends it.
- Contacts and Review Center allow explicit relationship types and manual high-impact event decisions.
- JVM/Room tests and debug APK build pass. Device capture and live API behavior still require target-device checks.

See `ANDROID_INTEGRATION_STATUS.md` and `CHANGELOG_V0.4.0.md`.

## Windows 个人 QQ 助手方向

- 已实现 NapCat OneBot 11 HTTP 事件接入、HMAC 签名校验、好友纯文本与自身消息入库、稳定 QQ ID 去重。
- 复用现有 SQLite / Session / Weight / Relationship 管线；AI Judge 保留原始意图，Reply 生成自然、关心、轻松三条候选。
- 自动发送为显式白名单模式，受 Judge 置信度、事件时效和 API token 门槛控制；发送失败保留候选且不自动重试。
- 主动联系任务默认检查 12 小时未聊天，仅针对单独白名单，具有时段、双向聊天、账号核对、Judge 和持久化防重门槛。
- Python 模拟事件单测已通过；真实 QQ 收发仍待本机安装并登录 NapCat 后验证。详见 `../QQ_BOT_WINDOWS.md`。
