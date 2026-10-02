# RelationshipEventDetector V1

## 四类来源

- `LOCAL_FACT`: 客观行为，可自动落账，如主动开启私聊。
- `LOCAL_SEMANTIC_RULE`: 强关键词/结构规则，只生成候选或高置信自动确认。
- `SEMANTIC_MODEL`: 未来语义增强，只返回标签和置信度。
- `MANUAL`: 用户手动确认。

## 关键政策

| 事件 | 默认政策 |
|---|---|
| INITIATE_PRIVATE_CHAT | AUTO_APPLY |
| TARGETED_SHARING | HIGH_CONFIDENCE_ONLY |
| CHECK_IN | HIGH_CONFIDENCE_ONLY |
| EMOTIONAL_SUPPORT | HIGH_CONFIDENCE_ONLY / model |
| LIGHT_FLIRT | HIGH_CONFIDENCE_ONLY / model |
| LIGHT_MISSING_EXPRESSION | HIGH_CONFIDENCE_ONLY |
| DIRECT_LIKE_EXPRESSION | USER_REVIEW |
| DIRECT_ROMANTIC_INTENT | USER_REVIEW |
| PURSUIT_EXPRESSION | USER_REVIEW |
| FRIEND_ONLY_EXPRESSION | USER_REVIEW |
| RELATIONSHIP_CONFIRMED | MANUAL_ONLY |
| RELATIONSHIP_ENDED | MANUAL_ONLY |

## 模型边界

模型输出 schema 中禁止存在 `relationship_score`、`stage`、`likes_user` 等字段。模型只能输出：

```json
{
  "events": [
    {
      "type": "EMOTIONAL_SUPPORT",
      "present": true,
      "confidence": 0.91,
      "actor": "SELF",
      "evidence": "你准备这么久肯定没问题"
    }
  ]
}
```
