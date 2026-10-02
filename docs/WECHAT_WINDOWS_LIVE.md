# Windows 微信实时采集

ChatWeight 现在已经接入 jev-chat-windows 的非侵入式 Windows 采集路线：

```text
WeChat / Weixin Windows 4.x
        ↓
Windows Graphics Capture (WGC)
        ↓
像素锚点定位消息区 / 会话标题
        ↓
RapidOCR 本地 OCR
        ↓
气泡颜色分类 me / her + 群聊发言人
        ↓
每会话 Reader 滚动去重
        ↓
ChatWeight WeChatSqliteIngestor
        ↓
UnifiedMessage
        ↓
SQLite messages + chat_sessions
```

## 运行环境

- Windows 10 / 11
- 微信 Windows 4.x（`Weixin.exe` / `WeChat.exe`）
- Python 3.11 或 3.12（建议 3.12）
- 微信窗口必须处于可渲染状态。可以被别的窗口遮住，但不能长期保持真正的最小化状态。

## 安装

在 `windows_agent` 目录运行：

```bat
install_wechat_windows.cmd
```

等价于：

```bat
python -m pip install -U pip
python -m pip install -e ".[wechat-windows]"
```

采集依赖只包括 WGC/OCR 路线需要的组件，不引入 Jev 的悬浮 UI 或大模型依赖：

- `windows-capture`
- `rapidocr-onnxruntime >=1.4,<2`
- `numpy`

## 启动

打开微信，并进入任意会话，然后运行：

```bat
run_wechat_live.cmd
```

或者：

```bat
python -m chatweight.wechat_live --db chatweight.db
```

默认行为：**第一次看到某个会话时只把当前屏幕内容作为去重基线，不写入旧消息。** 从下一条新出现的消息开始实时写库。因此重启 ChatWeight 不会把屏幕上当前可见的旧消息再次全部灌入数据库。

如果你明确希望第一次启动时把当前屏幕可见消息也写进去：

```bat
python -m chatweight.wechat_live --db chatweight.db --backfill-visible-on-first-frame
```

## 数据库

实时消息写入：

- `conversations`
- `persons`
- `platform_identities`
- `messages`
- `chat_sessions`

OCR 无法获得微信内部 message id / wxid / 原始发送时间，所以当前实现明确区分：

- `message_time`：ChatWeight **观察到该消息的时间**；不是微信数据库中的原始发送时间。
- 私聊 person id：由当前会话标题生成的平台内稳定 ID，不冒充 wxid。
- 群聊成员：由 `群名 + OCR 发言人名` 生成 group-scoped ID。不会因为两个群里都有“张三”就自动把他们合并。

## 私聊与群聊识别

- OCR 看到 incoming 消息带发言人名 → `group`
- OCR 看到 incoming 消息不带发言人名 → `private`
- 如果启动后第一批只有自己发出的消息，则暂时标成 `unknown`
- 后续一旦 incoming 消息证明它是私聊，会自动把早先该会话 `person_id IS NULL` 的消息回填到该私聊联系人

## 当前边界

1. 这是**看屏采集**，只记录当前微信正在展示/发生变化的会话，不读取微信数据库。
2. 不自动遍历所有未打开的会话。
3. 图片/表情/文件目前不会伪装成文本消息；这一版重点是可靠文本 OCR 入库。
4. OCR 可能有错字，因此 `confidence=0.90`，并把 OCR 来源信息写入 `raw_json`。
5. 当前会话标题不是稳定的微信官方 ID；用户改备注后可能被视为新会话，后续需要做“联系人合并”功能解决。

## 隐私

截图和 OCR 图像全程只存在内存。本模块不会把截图保存到磁盘，也不调用大模型。写入 SQLite 的只有标准化后的消息文本和必要的采集元数据。

## 上游来源

Windows WGC / OCR 核心路径基于 `jev-chat-windows` 的 MIT 代码适配：

https://github.com/jev-chat/jev-chat-windows

上游许可证和 NOTICE 位于：

`third_party/jev-chat-windows/`
