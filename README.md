# ChatWeight

本地聊天互动与关系进度分析工具，包含 Windows 微信采集、QQ 好友助手和 Android 应用。

**维护与新增功能：桔梗。** 本项目改编了 [Jev Windows](https://github.com/jev-chat/jev-chat-windows) 的采集/OCR 代码，以及 [Jev Android](https://github.com/jev-chat/jev-chat-jarvis) 的应用壳、采集适配器和可选回复功能。上游作者与原始版权保留，具体范围见 [第三方来源与许可](THIRD_PARTY_NOTICES.md)。

## 能做什么

| 模块 | 当前功能 |
| --- | --- |
| Windows 微信 | WGC 捕获当前可见会话，RapidOCR 识别文本；标准化、去重后写入本地 SQLite，并更新互动分析。首帧默认只建立基线。 |
| Windows QQ | 通过另行安装的 NapCat / OneBot 11 接收好友消息，更新本地分析；可选模型判断和三条候选回复。自动回复及长时间未联系后的主动消息需要分别显式开启并配置白名单。 |
| Android | Android 11+，QQ 与可选微信无障碍采集、ML Kit OCR、Room 本地分析、联系人关系类型与人工审核。AI 候选回复默认关闭，选中后只填入输入框，由用户发送。 |
| 本地核心 | 分别计算双方的主动度、响应度、投入量、持续度和联系频率；提供关系模板、事件流水、每日快照和关键关系事件审核。 |

本地分析无需模型密钥。启用 AI 回复后，会将受限聊天上下文和本地摘要发送给你配置的模型端点。

## 开始使用

完整克隆本仓库，保留各目录的相对位置：

```powershell
git clone https://github.com/fabfbaaf/chat-weight.git
cd chat-weight
```

Windows 微信建议 Python 3.11/3.12、Windows 10/11；适配目标为 Windows 微信 4.x。在 `windows_agent` 目录执行：

```bat
install_wechat_windows.cmd
run_wechat_live.cmd
```

默认数据文件为该目录下的 `chatweight.db`。采集需要微信窗口处于可渲染状态，具体步骤见 [微信采集指南](docs/WECHAT_WINDOWS_LIVE.md)。

其他入口：

- [Windows QQ 配置](docs/QQ_BOT_WINDOWS.md)：需要单独安装并登录 NapCat，分别配置事件接收和发送接口。
- [QQ 同机服务器部署](docs/QQ_BOT_SERVER.md)：服务、定时器和环境变量示例。
- [Android 使用与构建](android-app/README.md)：JDK 17+、Android SDK 35、Gradle Wrapper 8.9；从源码构建 Debug APK。
- [文档目录](docs/README.md)：架构、算法与历史记录。

## 验证

2026-10-02 在干净源码副本中完成：Python **58/58** 测试；Android Debug **12/12**、Release **12/12**、Kotlin core **1/1** 测试；Debug APK 构建成功。Android 验证使用 JDK 21、现有 SDK 与依赖缓存，未连接手机或真实聊天。

从 `windows_agent` 执行核心与模拟测试：

```powershell
python -B -m unittest discover -s tests -v
python -B -m chatweight.demo
```

从 `android-app` 执行：

```powershell
.\gradlew.bat test assembleDebug --no-daemon --max-workers=1
```

首次 Android 构建需要下载依赖。本次验证覆盖模拟数据和本地计算；真实微信/QQ 版本、Android 权限与后台采集、真实模型端点仍需在目标设备验证。Windows 实时采集额外依赖不属于 Python 核心测试范围。

## 工程与版本

```text
android-app/     Android 采集、Room、分析与可选回复
core-kotlin/     共享 Kotlin 权重与关系引擎
windows_agent/  Python 核心、SQLite、微信采集、QQ 助手
sql/            SQLite 表结构
shared/schema/  跨平台 JSON Schema
deploy/         QQ 服务与配置示例
docs/           当前指南、技术参考、历史归档
third_party/    上游原始许可证与 NOTICE
```

本次发布现有源码，不将组件版本改为 1.0。Android 为 **0.4.2 / versionCode 42**；Python 包元数据为 **0.2.0**。旧目录版本、阶段计划和变更记录保留在 [历史归档](docs/archive/README.md)，不代表当前验收结果。Windows 目前应从完整源码运行，SQL 路径依赖仓库布局。

## 数据与边界

- 互动权重表示行为投入，不能判断感情真假；关系 Stage 表示用户自己的表达进度，关键状态需要人工确认。
- 微信采集只读取当前可见会话，不读取微信数据库或自动遍历所有联系人。OCR 时间是观察时间，ID 为本地派生值；改备注可能需要人工处理身份。
- 图片、文件、语音的完整结构化识别与跨平台联系人合并界面尚未完成。
- 截图识别在内存中进行，消息文本与分析保存在本地数据库。模型回复功能有独立的网络配置；备份或分享时请自行选择要包含的数据。
- 仓库发布源码和示例配置，数据库、密钥、签名文件、缓存与聊天输出不纳入 Git。

## 许可

本项目新增代码与修改采用 [MIT License](LICENSE)，允许商用并须保留版权与许可声明。Jev 代码保留各自原始 MIT 版权；Gradle Wrapper、第三方依赖、SDK 与模型适用各自许可或条款，详见 [NOTICE](NOTICE.md) 与 [第三方声明](THIRD_PARTY_NOTICES.md)。项目署名不表示上游作者背书。
