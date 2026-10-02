# ChatWeight Android 0.4.2

Android 11+ 应用，包名 `io.chatweight.android`，`versionCode` 为 `42`。权重与关系计算复用同一仓库中的 `core-kotlin` 模块。

## 构建

需要 JDK 17 或更新版本、Android SDK Platform 35，以及可用的网络或完整依赖缓存。将 `JAVA_HOME` 指向所用 JDK，并配置 Android SDK 路径。

请完整克隆仓库，保留 `android-app` 与 `core-kotlin` 的同级目录关系；仅下载 `android-app` 无法构建。

从仓库根目录执行：

```powershell
cd android-app
.\gradlew.bat test assembleDebug --no-daemon --max-workers=1
```

macOS/Linux 使用 `bash ./gradlew test assembleDebug --no-daemon --max-workers=1`。首次构建会获取 Gradle 和依赖；缓存完整后可添加 `--offline`。

Debug APK 位于 `app/build/outputs/apk/debug/app-debug.apk`。

## 使用

1. 安装 APK，按首页提示开启无障碍、悬浮窗等权限。
2. 默认开启 QQ 采集，关闭微信采集和 AI Reply。需要微信时，在首页手动开启微信采集；正文节点不可读时可启用 OCR fallback。
3. 保持目标聊天窗口可见。首次看到一个会话时只建立去重基线，后续新增文本进入 Room、本地事件账本和每日快照。
4. 在“联系人”中设置关系类型，在 Review Center 中确认或拒绝高影响关系事件；`CRUSH` 不会自动指定，关键关系阶段需人工确认。

本地采集与分析不需要 API Key 或网络。AI Reply 需另行配置模型端点，使用有限的可见上下文与本地关系摘要，最多显示三条候选；选择候选只填入输入框，不会自动发送。

## 验证与边界

最新源码验证：Python 58 项、Kotlin/Android 25 项测试通过，Android 干净源码副本离线构建通过。命令与验证范围见[仓库 README](../README.md)。其中 Android Debug/Release 各 12 项，Kotlin 核心 1 项；这些是模拟测试，不代表真实聊天采集兼容性。

此次发布验证未进行真实 QQ/微信收发或模型端点联调。已有设备安装记录见 [0.4.1 更新记录](../docs/archive/CHANGELOG_V0.4.1.md)；新消息采集闭环、后台保活和权限流程仍需按机型与聊天应用版本实测。

当前主链处理文本；截图仅存于内存，无法可靠确定发言方的整屏 OCR 不参与评分。更多行为与设备限制见 [Android 集成记录](../docs/archive/ANDROID_INTEGRATION_STATUS.md)，最新测试结果以仓库 README 为准。
