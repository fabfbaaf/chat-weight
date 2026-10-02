# 第三方来源与许可

ChatWeight 的原创新增代码与修改由桔梗维护，发布账号为 fabfbaaf；该署名不替代下列上游作者的版权。除另有说明外，本项目原创新增代码与修改采用根目录 LICENSE 所载 MIT License。第三方源码、工具、SDK 和模型继续适用其原有许可或服务条款。

## Jev 聊天助手 Windows 版

- 项目：https://github.com/jev-chat/jev-chat-windows
- Copyright (c) 2026 rezoch340 and the jev-chat contributors
- Portions Copyright (c) 2026 Finderchangchang and the jev-chat contributors (Jev 聊天助手, https://github.com/jev-chat/jev-chat-jarvis)
- 许可：MIT。完整原文见 `third_party/jev-chat-windows/LICENSE`；上游原始声明见 `third_party/jev-chat-windows/NOTICE`。
- 实际改编文件：`windows_agent/chatweight/jev_windows/capture.py`、`ocr.py`、`worker.py`，分别来自上游 `app/capture.py`、`app/ocr.py`、`app/worker.py`；`__init__.py` 记录该模块的归属。
- 复用范围：Windows Graphics Capture、像素定位聊天区、RapidOCR 识别、发送者分类与每会话滚动去重。
- 现有工程没有记录最初改编时的 Windows 上游提交。本次 LICENSE / NOTICE 核验固定使用提交 `c6d3a10474ce1ff3b7f8f6402b3b5e0e58fad5f1`，该提交不代表原始导入版本。
- 本仓库的 Windows 采集模块没有引入上游 PySide6 / PySide6-Fluent-Widgets UI，也没有打包上游 Windows 发布包。上游 NOTICE 中对其发布包的 GPL / LGPL 组件说明应按该发布包的实际内容理解。

## Jev 聊天助手 Android 版

- 项目：https://github.com/jev-chat/jev-chat-jarvis
- 上游版本：v1.4；实际集成提交：`cccebcaedab61b2318376f6a68cd4127fb5190c9`。
- Copyright (c) 2026 Finderchangchang and the jev-chat contributors
- 许可：MIT。完整原文见 `third_party/jev-chat-jarvis/LICENSE`；上游原始声明见 `third_party/jev-chat-jarvis/NOTICE`。
- 复用范围：Android Activity / 设置与知识库应用壳、Accessibility 适配器与采集服务、屏幕捕获与 ML Kit OCR 调用、前台保活、浮动面板，以及 Jev 判断题目、判断 / 候选回复 / 视觉客户端。相应包名由 `com.jev.probe` 改为 `io.chatweight.android`；上游兼容服务类 `com.google.android.accessibility.selecttospeak.SelectToSpeakService` 保留。该服务类是上述上游项目的封装代码，不因其类名而成为 Google SDK 源码。
- 复用的资源包括 `android-app/app/src/main/res/` 下的启动图标、主题及无障碍配置 XML；Manifest 与构建配置基于同一上游工程调整。
- ChatWeight 的本地事件记账、Kotlin 权重 / 关系引擎、Room 数据层、摄取与分析流水线、联系人和关系 review，以及 Windows QQ OneBot 接入与主动联系等新增功能属于本项目的新增与修改。上游应用壳、采集适配器及回复功能仍应归属 Jev 作者。

以上归属说明不表示原作者对 ChatWeight 的背书。不得使用 Jev 名称或官网域名暗示由原作者出品或背书。

## Gradle Wrapper

- 工具版本：Gradle 8.9，配置见 `android-app/gradle/wrapper/gradle-wrapper.properties`。
- 文件：`android-app/gradlew`、`android-app/gradlew.bat`、`android-app/gradle/wrapper/gradle-wrapper.jar`。
- 许可：Apache-2.0，保留脚本内原版权和许可声明；许可原文见 `third_party/gradle/LICENSE-APACHE-2.0.txt`，本地 Wrapper JAR 内原始许可证见 `third_party/gradle/LICENSE-WRAPPER.txt`。
- 本地 Wrapper JAR SHA-256 与 Gradle 官方公布的 8.9 Wrapper 校验值一致：`498495120a03b9a6ab5d155f5de3c8f0d986a449153702fb80fc80e134484f17`。
- 官方校验值：https://services.gradle.org/distributions/gradle-8.9-wrapper.jar.sha256
- 完整 Gradle 8.9 上游许可（含其发行组件声明）另保留于 `third_party/gradle/LICENSE-GRADLE-8.9.txt`；保留该文件不表示本仓库打包了整套 Gradle 发行版。

## 独立运行依赖

以下组件在构建 / 安装时由各自发行源获取，不因被本项目调用而改为本项目的 MIT License。若发布包含依赖二进制或模型的安装包，须同时保留所含版本及传递依赖的许可与声明。

| 组件 | 本项目声明版本 | 许可 / 条款 | 官方来源 |
| --- | --- | --- | --- |
| NumPy | `>=1.26` | BSD-3-Clause | https://github.com/numpy/numpy/blob/main/LICENSE.txt |
| rapidocr-onnxruntime | `>=1.4,<2`，Python < 3.13 | Apache-2.0 | https://github.com/RapidAI/RapidOCR/blob/main/LICENSE |
| windows-capture | 未固定版本；仅 Windows | MIT，Copyright (c) 2023 NiiightmareXD | https://github.com/NiiightmareXD/windows-capture/blob/main/LICENCE |
| AndroidX core-ktx | 1.13.1 | Apache-2.0 | https://dl.google.com/dl/android/maven2/androidx/core/core-ktx/1.13.1/core-ktx-1.13.1.pom |
| AndroidX appcompat | 1.7.0 | Apache-2.0 | https://dl.google.com/dl/android/maven2/androidx/appcompat/appcompat/1.7.0/appcompat-1.7.0.pom |
| AndroidX constraintlayout | 2.1.4 | Apache-2.0 | https://dl.google.com/dl/android/maven2/androidx/constraintlayout/constraintlayout/2.1.4/constraintlayout-2.1.4.pom |
| AndroidX Room runtime / ktx | 2.6.1 | Apache-2.0 | https://dl.google.com/dl/android/maven2/androidx/room/room-runtime/2.6.1/room-runtime-2.6.1.pom |
| Material Components for Android | 1.12.0 | Apache-2.0 | https://github.com/material-components/material-components-android/blob/1.12.0/LICENSE |
| ML Kit Chinese text recognition SDK / bundled model | 16.0.1 | ML Kit Terms of Service（并纳入 Google APIs Terms of Service） | https://developers.google.com/ml-kit/terms |

ML Kit 16.0.1 的官方 POM 将其许可明确标为 ML Kit Terms of Service： https://dl.google.com/dl/android/maven2/com/google/mlkit/text-recognition-chinese/16.0.1/text-recognition-chinese-16.0.1.pom 。SDK 和中文模型均不属于本项目 MIT 授权范围。

QQ 接入通过公开 OneBot 11 协议连接另行安装的网关（例如 NapCat）。本仓库没有因此包含 NapCat 源码或其发行包；网关本身适用自己的许可。
