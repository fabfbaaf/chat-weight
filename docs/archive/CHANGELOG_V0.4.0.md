# ChatWeight V0.4.0 Android

## Changes

- Restored an installable Android 11+ app from `jev-chat-jarvis` commit `cccebcaedab61b2318376f6a68cd4127fb5190c9`, with ChatWeight package/branding and upstream MIT attribution.
- Wired QQ and opt-in WeChat Accessibility/OCR capture to `UnifiedMessage`, Room and the shared `core-kotlin` Weight/Relationship engines. The first visible screen primes dedupe; later messages on both sides enter the local pipeline. OCR with unknown sender side is not scored.
- Added Room entities/DAOs for the shared data protocol, persisted per-conversation capture cursors, replay guards, 30-minute session restore, weight/relationship event ledgers and daily snapshots.
- Added Contacts relationship-type controls and Review Center for manual confirm/reject. High-impact candidates do not change Stage 5 or 6 before confirmation.
- Added optional AI Reply: intent Judge, three reply drafts, ranking, short relationship context and overlay fill. No model key is needed for local analysis; no message is auto-sent. Custom OpenAI-compatible chat-completions Judge is supported alongside the upstream Jev decisions route.
- Added home controls for capture, OCR, AI and local database counts, plus clearer permission, service and data-storage notices.

## Verification

- Windows Python: 15 tests passed; includes SQLite schema verification.
- Kotlin core executable tests: passed.
- Android Gradle `test assembleDebug`: passed in the final build.
- Android JVM/Room: normalization, duplicate text, per-conversation cursor, fingerprint uniqueness, session restore, event ledger, manual Stage 5/6 gates, daily snapshots, cascade delete and AI-off local path covered.
- Debug APK: `android-app/app/build/outputs/apk/debug/app-debug.apk`.

## Limits

No Android device or live model endpoint was available for validation. QQ 9.3.50 and WeChat 8.0.78 are upstream reference versions only. The current upstream commit disables WeChat; ChatWeight leaves its adapter available behind an explicit off-by-default switch. OCR rejection and app-version compatibility need target-device testing. Current local capture is text-focused; whole-screen OCR without a reliable speaker side does not affect relationship scores. Cross-platform contact merging is outside V0.4.
