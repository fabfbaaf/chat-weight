# ChatWeight QQ 助手：服务器部署准备

目标拓扑是 **NapCat 与 ChatWeight 运行在同一台服务器**。使用 NapCat 的 Linux Shell 安装方式时，两者可通过 `127.0.0.1` 通信；NapCat 的 [Linux 安装说明](https://doc.napneko.icu/guide/boot/Shell)和 [网络配置说明](https://doc.napneko.icu/config/basic)由上游维护。

```text
QQ ↔ NapCat
       ├─ HTTP 客户端 → 127.0.0.1:8765/onebot/event → ChatWeight
       └─ HTTP 服务端 ← 127.0.0.1:3000/send_private_msg ← ChatWeight
ChatWeight → SQLite / 关系分析 / LLM Judge + Reply
15 分钟定时器 → 满 12 小时的白名单好友 → AI Judge → 可选主动发送
```

NapCat HTTP 客户端配置 `token`，ChatWeight 配置同值 `CHATWEIGHT_ONEBOT_SECRET`，事件签名由 ChatWeight 校验。NapCat HTTP 服务端另设 `token`，ChatWeight 用 `CHATWEIGHT_ONEBOT_TOKEN` 调用发送接口。两个 HTTP 端口均绑定本机，不需要向公网开放。NapCat 的 HTTP 客户端打开 `reportSelfMessage`，让手动发送的 QQ 消息也参加双方关系计算。详细字段见 [Windows 联调说明](QQ_BOT_WINDOWS.md)。

## LLM 接口

目前的 `QQReplyEngine` 使用 OpenAI 兼容的 `/chat/completions` 请求，判断与回复可配置不同模型：

```text
CHATWEIGHT_AI_BASE_URL=https://模型服务地址/v1
CHATWEIGHT_AI_KEY=模型密钥
CHATWEIGHT_JUDGE_MODEL=判断模型名
CHATWEIGHT_REPLY_MODEL=回复模型名
```

外部模型地址要求 HTTPS。若使用同机本地模型且它提供兼容接口，可以使用 `http://127.0.0.1:<端口>/v1`，此时允许不设 `CHATWEIGHT_AI_KEY`。**LLM 厂商尚未确定**；如最终服务只提供非兼容 API，需要在 `qq_reply.py` 增加对应客户端适配，不能仅替换 URL。

没有配置 LLM 时，消息仍会入库并更新 Session / Weight / Relationship，候选为空。配置 LLM 后，Judge 会先分析原始意图，再生成自然、关心、轻松三条候选，保存在 `qq_suggestions.json`；自动发送默认关闭。

## 进程与持久化

仓库提供 [监听服务示例](../deploy/chatweight-qq.service.example)、[主动联系服务示例](../deploy/chatweight-qq-proactive.service.example)、[15 分钟定时器示例](../deploy/chatweight-qq-proactive.timer.example)和[环境变量示例](../deploy/chatweight-qq.env.example)。按服务器实际路径调整 `WorkingDirectory` 和 Python 位置，将环境文件放到 `/etc/chatweight/qq.env`，并给运行账户读取权限。`chatweight.db`、SQLite WAL 文件与两个建议 JSON 文件需保存在持久目录，例如 `/var/lib/chatweight`。

先在 NapCat 完成 QQ 登录，并运行 `python3 -m chatweight.qq_bot --check-account` 核对 `CHATWEIGHT_QQ_SELF_ID`。服务默认只产候选。要在收到新消息后自动回复，在监听服务的 `ExecStart` 增加 `--auto-send --allow-user-id <测试好友QQ号>`；可重复写白名单参数。自动回复要求已配置本人 QQ 号、Judge 置信度至少 0.7、消息不超过 2 分钟、距本会话上次发言至少 20 秒；发送失败不会自动重试。

主动联系使用独立的 one-shot 服务和定时器，不会阻塞实时监听。`CHATWEIGHT_QQ_PROACTIVE_ALLOW_IDS` 是只允许主动联系的好友 QQ 号列表，`CHATWEIGHT_QQ_SELF_ID` 是 NapCat 当前登录的本人 QQ 号；主动联系服务默认 `--send`，请先不加此参数手动预览候选。每 15 分钟检查一次，最后一条消息满 12 小时且处于北京时间 10:00–21:00、存在双方聊天历史、没有未答的己方问句、Judge 置信度至少 0.85 才发送。每个好友每天最多一次尝试；对方没有新回复前不会再次追发。

示例运行命令（从 `windows_agent` 目录执行）：

```bash
python3 -m chatweight.qq_bot \
  --db /var/lib/chatweight/chatweight.db \
  --suggestions /var/lib/chatweight/qq_suggestions.json
```

`GET http://127.0.0.1:8765/health` 只返回监听状态和队列长度。当前候选通过本地 JSON 文件读取，尚无远程管理页面。若 NapCat 跑在容器里，容器的 `127.0.0.1` 与宿主机不是同一个网络空间；这份本机回环配置需要改为受控容器网络后才能使用。

本仓库已经完成模拟 OneBot 事件、AI 响应及 12 小时主动联系的自动化测试；**尚未在目标服务器上安装 NapCat、登录 QQ 或调用实际 LLM 完成端到端验证**。
