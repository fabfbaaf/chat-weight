# Semantic Model Contract

模型只能做事件标签分类，不能输出或改变关系状态。

## 输入建议

只给：当前目标消息 + 前3条 + 后2条 + 必要时1条历史关联消息。

## 禁止字段

- relationship_score
- stage
- likes_user
- probability_of_love
- relationship_confirmed

## 输出

严格匹配 `shared/schema/semantic-event-response.schema.json`。

关键状态事件（明确表白、关系确认、关系结束）不开放给自动语义接口直接落账，统一走 Review/Manual 流程。
