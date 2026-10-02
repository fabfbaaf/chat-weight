# Android V0.4 integration status

## Integrated source

Upstream: `jev-chat-jarvis`, commit `cccebcaedab61b2318376f6a68cd4127fb5190c9`. MIT license and upstream NOTICE are retained under `third_party/jev-chat-jarvis/`. The imported Android app provides its activity/settings shell, Accessibility service, QQ and WeChat adapters, screenshot and ML Kit OCR, foreground keepalive and floating reply panel. Package and visible product name are ChatWeight. The special `com.google.android.accessibility.selecttospeak.SelectToSpeakService` class remains for WeChat compatibility.

The Android app depends directly on the existing `core-kotlin` Gradle module. Message normalization, Room mapping, session restore, local event ledger, WeightEngine, RelationshipEngine, candidate review and daily snapshots are wired behind a single background ingest queue. Android does not have a second Weight/Relationship algorithm implementation. AI Reply runs only after local ingestion and can be turned off independently.

## Current behavior

- QQ Accessibility capture defaults on. Both incoming and outgoing visible text are normalized and inserted. Group nickname mapping is used only when a sender label is present; unknown sender stays null.
- WeChat Accessibility and OCR support are present but default off. Users must opt in on the home screen. This reflects the current upstream commit, which disables WeChat capture due compatibility/risk-control concerns.
- First visible screen primes the per-conversation cursor. Later screen tails are written with a sequence-based fingerprint. Current capture time is an observation time, not the chat app's original message timestamp.
- Room contains the shared-schema tables plus a capture cursor. Message insert, derived events, state and cursor update share one transaction. A processed-message marker prevents pipeline replay.
- Relationship type defaults to FRIEND. Contacts allows explicit type selection. Review Center handles pending high-impact events. No unreviewed direct expression or relationship confirmation can raise Stage 5/6.
- When AI Reply is enabled and keys are configured, Judge → Reply → Rank produces up to three candidates in the overlay; the user can fill but must send manually. The Jev decisions route and a custom OpenAI-compatible chat-completions judge route are supported. AI Reply gets at most ten visible lines and a short relationship summary.
- Without a model key or network, local capture, Room, Weight and Relationship remain available.

## Verification

- Existing Windows Python tests: 15 passed before Android changes; rerun in the final acceptance pass.
- Existing Kotlin core executable tests: passed before Android changes; Gradle `:core:test` passed.
- Android JVM tests cover QQ/WeChat normalization, duplicate events, identical consecutive text, conversation isolation, Room fingerprint uniqueness, session restore/30-minute split, weight ledger, daily snapshots, manual Stage 5/6 gates and cascade deletion.
- Android Gradle test and debug build results are recorded in `CHANGELOG_V0.4.0.md` after final verification.

## Device validation still required

No Android phone was connected during this development pass. QQ 9.3.50 group chat and WeChat 8.0.78 are upstream reference versions, not verified ChatWeight results. Verify one-to-one/group titles, sender position, duplicate events, OCR rejection/backoff, background keepalive and permission flow on target devices before relying on scores. WeChat may expose no readable nodes or reject screenshots. Flat whole-screen OCR has no trustworthy speaker side, so it is deliberately excluded from relationship scoring. Non-text media recognition and cross-platform identity merging are not implemented.
