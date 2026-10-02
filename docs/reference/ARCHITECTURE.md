# Architecture

```text
WeChat Windows / QQ Android / Import
              │
              ▼
       ChatCaptureAdapter
              │
              ▼
        UnifiedMessage
              │
      ┌───────┴────────┐
      ▼                ▼
 SessionManager    MessageRepository
      │
      ▼
 WeightEventDetector ─────► WeightEngine ─────► weight_events / weight_state
      │
      ▼
 RelationshipEventDetector
      │
      ▼
 Candidate + ConfirmationPolicy
      │
      ▼
 RelationshipEngine ─────► relationship_events / relationship_profile
              │
              ▼
       DailySnapshotJob
```

## 分层约束

- `capture` 不知道任何分值。
- `weight` 不知道微信/QQ如何抓取。
- `relationship` 不允许模型直接决定 Stage 5/6 或关系结束。
- 跨端协议只依赖 `UnifiedMessage`、事件枚举和数据库字段。
