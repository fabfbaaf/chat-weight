# Jev 接入计划

本工程把 Jev 当作采集层参考，而不是把回复助手内核作为核心依赖。

## Android / QQ

建议把 Jev 的 Accessibility QQ Adapter 包到：

```text
android-app/.../capture/QQAndroidAdapter.kt
```

输出统一 `UnifiedMessage`，不要直接调用回复模型。

## Windows / 微信

建议把 Jev Windows 的窗口捕获/OCR/worker 包到：

```text
windows_agent/chatweight/adapters/wechat_windows.py
```

输出统一 `UnifiedMessage` 并写入 SQLite。

## 不应进入核心的 Jev 功能

- 候选回复生成
- 候选回复排序
- 自动填入回复
- 依赖大段聊天上下文的回复 Prompt

这些以后可以作为独立 Reply Assistant 插件回归。
