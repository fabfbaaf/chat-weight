# ChatWeight Android V0.4.1 — 微信实时采集修复

## 修复

- 微信处于前台时每 4 秒主动复查当前聊天窗口，补上部分手机漏报无障碍内容变化事件的情况。
- 微信气泡容器本身没有正文时，继续读取子节点文字；气泡左右侧用边缘位置判断。
- 气泡几何位置没有变化时，允许 OCR 在 2.5 秒后重试；会话标题缺失时尝试从截图顶部识别。
- 首页显示微信版本、采集状态和最近一次新消息入库时间；入库异常会显示在状态中。
- 离开微信后丢弃未完成的 OCR 结果，避免写入错误会话。

## 验证

- `android-app/gradlew.bat test assembleDebug --no-daemon --max-workers=1`：通过。
- Debug APK 已安装到 Vivo V2238A，微信版本 8.0.77。
- 实时消息闭环仍须在手机开启无障碍、微信采集和 OCR fallback 后，用实际新消息验证。

## 安装包

`android-app/app/build/outputs/apk/debug/app-debug.apk`
