# ChatWeight Windows 个人 QQ 好友助手

这条链路使用 Windows 本机运行的 NapCat 将个人 QQ 好友消息按 OneBot 11 上报给 ChatWeight。NapCat 是单独安装、单独登录的第三方协议端；ChatWeight 不读取 QQ 私有数据库。代码路径是 `windows_agent/chatweight/qq_onebot.py`、`qq_bot.py` 和 `qq_reply.py`。

```text
NapCat 私聊事件 → UnifiedMessage → SQLite / Session / Weight / Relationship
                                      → AI Judge（保留原始意图）
                                      → 自然 / 关心 / 轻松 3 条候选
                                      → 可选：白名单好友自动发送自然回复
```

## 1. 配置 NapCat

在 [NapCat WebUI](https://doc.napneko.icu/config/basic) 的网络配置里建立并启用两项，均只绑定/连接本机：

| NapCat 项 | 设置 | 用途 |
| --- | --- | --- |
| HTTP 客户端 | URL `http://127.0.0.1:8765/onebot/event`；消息格式 `array`；打开“上报自身消息”；设置一个事件 `token` | 推送好友消息和自己的手动回复 |
| HTTP 服务端 | Host `127.0.0.1`；Port `3000`；设置另一个 API `token` | 自动发送时调用 `send_private_msg` |

两个 token 可以不同。**HTTP 客户端的 token** 要填到 `CHATWEIGHT_ONEBOT_SECRET`。NapCat 会用它对 HTTP 上报正文计算 HMAC-SHA1，写入 `X-Signature`；ChatWeight 会核对签名。**HTTP 服务端的 token** 要填到 `CHATWEIGHT_ONEBOT_TOKEN`，用于发消息时的 `Authorization: Bearer`。这是两个不同方向的连接，WebUI 登录 token 也与它们分开。配置行为可在 NapCat 的 [HTTP 客户端源码](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/network/http-client.ts)和 [HTTP 服务端源码](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/network/http-server.ts)核对。

若不启用“上报自身消息”，分析只能看到对方的消息和本助手代发的消息，无法统计你在 QQ 客户端里手动发送的内容。当前只处理 `private` + `friend` 的纯文本事件；群聊、临时会话、图片、混合媒体不会触发回复。

## 2. 启动 ChatWeight

需要 Python 3.11+。在 PowerShell 中打开 `chat-weight-v1/windows_agent`，给当前终端设置配置：

```powershell
$env:CHATWEIGHT_ONEBOT_SECRET = '填 NapCat HTTP 客户端 token'
$env:CHATWEIGHT_ONEBOT_TOKEN = '填 NapCat HTTP 服务端 token'
$env:CHATWEIGHT_QQ_SELF_ID = '填当前登录 NapCat 的本人 QQ 号'
$env:CHATWEIGHT_AI_BASE_URL = 'https://你的 OpenAI 兼容服务/v1'
$env:CHATWEIGHT_AI_KEY = '填模型 API Key'
$env:CHATWEIGHT_JUDGE_MODEL = '填判断模型名'
$env:CHATWEIGHT_REPLY_MODEL = '填回复模型名'
python -m chatweight.qq_bot --check-account
python -m chatweight.qq_bot --db chatweight.db
```

先在 NapCat 登录个人 QQ，再运行 `--check-account`。它调用本机 OneBot `get_login_info` 并打印当前登录的 QQ 号；如果与 `CHATWEIGHT_QQ_SELF_ID` 不一致就报错。ChatWeight 自身不负责登录 QQ。登录完成后才启动事件监听；自动发送模式在启动时及每次发送前再次核对账号。

也可以运行 `run_qq_bot.cmd`，它把命令行参数原样传给 Python。若不配置 LLM，好友文本依然会入库并更新本地关系分析，但不会生成候选。同机本地 LLM 的 OpenAI 兼容接口可使用 `http://127.0.0.1:<端口>/v1`，不要求 API Key。AI 开启后，最新三条候选写入 `windows_agent/qq_suggestions.json`，以好友 QQ 号作为键；文件包含聊天回复文本，请保存在自己的本机目录。模型只接收该好友最近 12 条文本与简短关系摘要。

先保持上述默认模式观察候选。需要自动发送时，使用：

```powershell
python -m chatweight.qq_bot --db chatweight.db --auto-send --allow-user-id 123456789
```

把 `123456789` 换成**明确允许自动回复的好友 QQ 号**；多个好友可重复写 `--allow-user-id`。自动发送必须配置 `CHATWEIGHT_QQ_SELF_ID`，并要求 AI Judge 判断应该回复、置信度至少 0.7、有自然候选、事件到达不超过 2 分钟，并且距本会话上次发言至少 20 秒。自动发送默认关闭。发送失败时保留三条候选，不自动重试，以免网关已发送但返回失败时重复发言。回复由用户自己的 QQ 号发出，使用前先用测试好友验证语气与白名单。

## 3. 12 小时未聊天后主动联系

此任务按次运行，适合每 15 分钟调度一次。只扫描指定好友白名单，且双方此前都至少发过一条消息。最后一条消息距今满 12 小时、当前在北京时间 10:00–21:00、没有未答的己方问句、此前主动联系后对方已有新回复时，才进入 AI Judge。Judge 同意且置信度至少 0.85 后，生成三条低压力开场消息；加 `--send` 才自动发出其中的自然版本。

```powershell
$env:CHATWEIGHT_QQ_PROACTIVE_ALLOW_IDS = '123456789,987654321'
python -m chatweight.qq_proactive --db chatweight.db
python -m chatweight.qq_proactive --db chatweight.db --send
```

第一条是预览模式，候选写入 `qq_proactive_suggestions.json`，不会发送。第二条适合配置好定时任务后运行；发送记录保存在 SQLite 的 `qq_proactive_attempts`。同一好友一天最多尝试一次，结果不确定时不重试；对方未回复前也不会再次主动追发。Windows 任务计划程序需要让运行账户持有上述环境变量，并设为每 15 分钟执行一次 `run_qq_proactive.cmd --db <数据库绝对路径> --send`。建议为数据库和候选文件都使用绝对路径，确保监听器和定时任务使用同一份 SQLite。

健康检查：`http://127.0.0.1:8765/health`。收到好友消息后终端会打印 `analyzed`、`sent` 或 `send_failed` 和数据库消息总数；不打印聊天正文。`qq_suggestions.json` 的 `auto_sent` 字段表示这条候选是否由助手发送。分析数据在 `chatweight.db` 中；自动发出的消息会作为 `OUTGOING` 回写，NapCat 再上报同一条时按消息 ID 去重。

## 验证范围

本仓库的模拟 OneBot 事件测试覆盖签名、好友过滤、自己消息、去重、SQLite 分析、Judge/三条候选与自动发送白名单。**当前工作机尚未检测到运行中的 NapCat/QQ 进程，因此尚未完成真实 QQ 好友的收发端到端测试。**真机联调时先保持自动发送关闭，确认 `qq_suggestions.json` 随新消息更新，再只对白名单测试好友开启发送。

个人 QQ 好友聊天属于 NapCat 的非官方协议接入场景；[QQ 官方机器人 C2C 接口](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/c2c_message_create.html)面向机器人身份，不提供普通个人 QQ 账号的好友聊天读取接口。

未来 NapCat 与 ChatWeight 同机放到服务器的配置见 [服务器部署准备](QQ_BOT_SERVER.md)。
