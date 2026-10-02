from __future__ import annotations

from dataclasses import dataclass

from .models import (
    RelationshipEventCategory,
    RelationshipEventType,
    WeightDimension,
    WeightEventType,
)


@dataclass(frozen=True, slots=True)
class WeightRule:
    event_type: WeightEventType
    dimension: WeightDimension
    base_delta: float
    repeatable: bool = True
    repeat_group: str | None = None
    max_per_session: int | None = None
    base_share: float = 0.25


WEIGHT_RULES: dict[WeightEventType, WeightRule] = {
    WeightEventType.SESSION_START: WeightRule(WeightEventType.SESSION_START, WeightDimension.INITIATIVE, 3.0, repeatable=False),
    WeightEventType.FOLLOW_UP_WITHOUT_REPLY: WeightRule(WeightEventType.FOLLOW_UP_WITHOUT_REPLY, WeightDimension.INITIATIVE, 0.8, repeat_group="follow_up"),
    WeightEventType.DIRECT_MENTION: WeightRule(WeightEventType.DIRECT_MENTION, WeightDimension.INITIATIVE, 0.6),
    WeightEventType.DIRECT_QUOTE: WeightRule(WeightEventType.DIRECT_QUOTE, WeightDimension.RESPONSE, 0.3),
    WeightEventType.GROUP_GENERAL_MESSAGE: WeightRule(WeightEventType.GROUP_GENERAL_MESSAGE, WeightDimension.INITIATIVE, 0.1),
    WeightEventType.REPLY_WITHIN_1M: WeightRule(WeightEventType.REPLY_WITHIN_1M, WeightDimension.RESPONSE, 1.2, repeat_group="reply_speed"),
    WeightEventType.REPLY_WITHIN_5M: WeightRule(WeightEventType.REPLY_WITHIN_5M, WeightDimension.RESPONSE, 1.0, repeat_group="reply_speed"),
    WeightEventType.REPLY_WITHIN_15M: WeightRule(WeightEventType.REPLY_WITHIN_15M, WeightDimension.RESPONSE, 0.7, repeat_group="reply_speed"),
    WeightEventType.REPLY_WITHIN_60M: WeightRule(WeightEventType.REPLY_WITHIN_60M, WeightDimension.RESPONSE, 0.4, repeat_group="reply_speed"),
    WeightEventType.REPLY_WITHIN_6H: WeightRule(WeightEventType.REPLY_WITHIN_6H, WeightDimension.RESPONSE, 0.1, repeat_group="reply_speed"),
    WeightEventType.QUESTION_UNANSWERED_24H: WeightRule(WeightEventType.QUESTION_UNANSWERED_24H, WeightDimension.RESPONSE, -0.5),
    WeightEventType.MULTIPLE_QUESTIONS_UNANSWERED: WeightRule(WeightEventType.MULTIPLE_QUESTIONS_UNANSWERED, WeightDimension.RESPONSE, -0.8),
    WeightEventType.LONG_REPLY_1_5X: WeightRule(WeightEventType.LONG_REPLY_1_5X, WeightDimension.EFFORT, 0.3, repeat_group="long_reply"),
    WeightEventType.LONG_REPLY_3X: WeightRule(WeightEventType.LONG_REPLY_3X, WeightDimension.EFFORT, 0.7, repeat_group="long_reply"),
    WeightEventType.LONG_REPLY_6X: WeightRule(WeightEventType.LONG_REPLY_6X, WeightDimension.EFFORT, 1.0, repeat_group="long_reply"),
    WeightEventType.BURST_2_3: WeightRule(WeightEventType.BURST_2_3, WeightDimension.EFFORT, 0.2),
    WeightEventType.BURST_4_PLUS: WeightRule(WeightEventType.BURST_4_PLUS, WeightDimension.EFFORT, 0.4),
    WeightEventType.SEND_IMAGE: WeightRule(WeightEventType.SEND_IMAGE, WeightDimension.EFFORT, 0.1),
    WeightEventType.SEND_STICKER: WeightRule(WeightEventType.SEND_STICKER, WeightDimension.EFFORT, 0.05),
    WeightEventType.SEND_LINK: WeightRule(WeightEventType.SEND_LINK, WeightDimension.EFFORT, 0.2),
    WeightEventType.SEND_FILE: WeightRule(WeightEventType.SEND_FILE, WeightDimension.EFFORT, 0.4),
    WeightEventType.SEND_VOICE_10_30S: WeightRule(WeightEventType.SEND_VOICE_10_30S, WeightDimension.EFFORT, 0.3),
    WeightEventType.SEND_VOICE_30_60S: WeightRule(WeightEventType.SEND_VOICE_30_60S, WeightDimension.EFFORT, 0.5),
    WeightEventType.SEND_VOICE_60S_PLUS: WeightRule(WeightEventType.SEND_VOICE_60S_PLUS, WeightDimension.EFFORT, 0.8),
    WeightEventType.SHORT_REPLY_CHAIN_3: WeightRule(WeightEventType.SHORT_REPLY_CHAIN_3, WeightDimension.EFFORT, -0.4, max_per_session=1),
    WeightEventType.SHORT_REPLY_CHAIN_5: WeightRule(WeightEventType.SHORT_REPLY_CHAIN_5, WeightDimension.EFFORT, -0.5, max_per_session=1),
    WeightEventType.SESSION_4_TURNS: WeightRule(WeightEventType.SESSION_4_TURNS, WeightDimension.CONTINUITY, 0.4, repeatable=False),
    WeightEventType.SESSION_8_TURNS: WeightRule(WeightEventType.SESSION_8_TURNS, WeightDimension.CONTINUITY, 0.6, repeatable=False),
    WeightEventType.SESSION_15_TURNS: WeightRule(WeightEventType.SESSION_15_TURNS, WeightDimension.CONTINUITY, 1.0, repeatable=False),
    WeightEventType.SESSION_30_TURNS: WeightRule(WeightEventType.SESSION_30_TURNS, WeightDimension.CONTINUITY, 1.5, repeatable=False),
    WeightEventType.SESSION_20_MIN: WeightRule(WeightEventType.SESSION_20_MIN, WeightDimension.CONTINUITY, 0.4, repeatable=False),
    WeightEventType.SESSION_60_MIN: WeightRule(WeightEventType.SESSION_60_MIN, WeightDimension.CONTINUITY, 0.8, repeatable=False),
    WeightEventType.SESSION_120_MIN: WeightRule(WeightEventType.SESSION_120_MIN, WeightDimension.CONTINUITY, 1.0, repeatable=False),
    WeightEventType.ACTIVE_DAY: WeightRule(WeightEventType.ACTIVE_DAY, WeightDimension.FREQUENCY, 0.6, repeatable=False),
    WeightEventType.ACTIVE_STREAK_3D: WeightRule(WeightEventType.ACTIVE_STREAK_3D, WeightDimension.FREQUENCY, 0.5, repeatable=False),
    WeightEventType.ACTIVE_STREAK_7D: WeightRule(WeightEventType.ACTIVE_STREAK_7D, WeightDimension.FREQUENCY, 1.0, repeatable=False),
    WeightEventType.ACTIVE_STREAK_14D: WeightRule(WeightEventType.ACTIVE_STREAK_14D, WeightDimension.FREQUENCY, 1.5, repeatable=False),
    WeightEventType.ACTIVE_3_DAYS_WEEK: WeightRule(WeightEventType.ACTIVE_3_DAYS_WEEK, WeightDimension.FREQUENCY, 0.5, repeatable=False),
    WeightEventType.ACTIVE_5_DAYS_WEEK: WeightRule(WeightEventType.ACTIVE_5_DAYS_WEEK, WeightDimension.FREQUENCY, 1.0, repeatable=False),
}


@dataclass(frozen=True, slots=True)
class RelationshipRule:
    event_type: RelationshipEventType
    category: RelationshipEventCategory
    progress_delta: float
    heat_delta: float
    repeat_group: str | None = None
    max_per_session: int | None = None
    max_per_day: int | None = None
    requires_self_actor: bool = True


def rr(t, c, p, h, repeat_group=None, max_per_session=None, max_per_day=None, requires_self_actor=True):
    return RelationshipRule(t, c, p, h, repeat_group, max_per_session, max_per_day, requires_self_actor)


RELATIONSHIP_RULES = {
    r.event_type: r
    for r in [
        rr(RelationshipEventType.PERSONAL_TOPIC, RelationshipEventCategory.FAMILIARITY, 0.3, 0.5, "personal_topic", max_per_day=3),
        rr(RelationshipEventType.PERSONAL_QUESTION, RelationshipEventCategory.FAMILIARITY, 0.5, 0.7, "personal_question", max_per_day=3),
        rr(RelationshipEventType.SELF_DISCLOSURE, RelationshipEventCategory.FAMILIARITY, 0.8, 1.0, "self_disclosure", max_per_day=3),
        rr(RelationshipEventType.SHARED_EXPERIENCE, RelationshipEventCategory.FAMILIARITY, 0.8, 1.0, max_per_day=2),
        rr(RelationshipEventType.INITIATE_PRIVATE_CHAT, RelationshipEventCategory.APPROACH, 1.0, 1.5, "approach", max_per_day=3),
        rr(RelationshipEventType.TARGETED_SHARING, RelationshipEventCategory.APPROACH, 1.0, 1.5, max_per_day=3),
        rr(RelationshipEventType.CONTINUE_CONVERSATION, RelationshipEventCategory.APPROACH, 0.5, 0.7, "continue", max_per_session=2),
        rr(RelationshipEventType.INITIATE_VOICE_CALL, RelationshipEventCategory.APPROACH, 1.2, 1.8, max_per_day=2),
        rr(RelationshipEventType.INITIATE_ACTIVITY, RelationshipEventCategory.APPROACH, 1.2, 1.8, max_per_day=2),
        rr(RelationshipEventType.INITIATE_MEETUP, RelationshipEventCategory.APPROACH, 2.0, 2.5, max_per_day=1),
        rr(RelationshipEventType.CHECK_IN, RelationshipEventCategory.CARE, 1.0, 1.5, max_per_day=3),
        rr(RelationshipEventType.REMEMBER_AND_FOLLOW_UP, RelationshipEventCategory.CARE, 1.5, 2.0, max_per_day=2),
        rr(RelationshipEventType.EMOTIONAL_SUPPORT, RelationshipEventCategory.CARE, 1.5, 2.0, max_per_day=3),
        rr(RelationshipEventType.PRACTICAL_SUPPORT, RelationshipEventCategory.CARE, 1.2, 1.5, max_per_day=3),
        rr(RelationshipEventType.SAFETY_CONCERN, RelationshipEventCategory.CARE, 0.8, 1.2, max_per_day=3),
        rr(RelationshipEventType.SPECIAL_DATE_ATTENTION, RelationshipEventCategory.CARE, 1.5, 2.0, max_per_day=1),
        rr(RelationshipEventType.SPECIAL_COMPLIMENT, RelationshipEventCategory.AFFECTION, 1.0, 1.5, max_per_day=2),
        rr(RelationshipEventType.SPECIAL_NICKNAME, RelationshipEventCategory.AFFECTION, 1.5, 1.5, max_per_day=2),
        rr(RelationshipEventType.LIGHT_FLIRT, RelationshipEventCategory.AFFECTION, 2.5, 3.0, max_per_day=2),
        rr(RelationshipEventType.LIGHT_MISSING_EXPRESSION, RelationshipEventCategory.AFFECTION, 3.0, 3.5, max_per_day=2),
        rr(RelationshipEventType.CARE_EXPRESSION, RelationshipEventCategory.AFFECTION, 2.0, 2.5, max_per_day=2),
        rr(RelationshipEventType.DEPENDENCY_EXPRESSION, RelationshipEventCategory.AFFECTION, 2.0, 2.5, max_per_day=2),
        rr(RelationshipEventType.SPECIAL_IMPORTANCE_EXPRESSION, RelationshipEventCategory.AFFECTION, 3.0, 3.5, max_per_day=2),
        rr(RelationshipEventType.DIRECT_LIKE_EXPRESSION, RelationshipEventCategory.DIRECT_EXPRESSION, 10.0, 8.0, max_per_day=1),
        rr(RelationshipEventType.DIRECT_ROMANTIC_INTENT, RelationshipEventCategory.DIRECT_EXPRESSION, 10.0, 8.0, max_per_day=1),
        rr(RelationshipEventType.PURSUIT_EXPRESSION, RelationshipEventCategory.DIRECT_EXPRESSION, 10.0, 8.0, max_per_day=1),
        rr(RelationshipEventType.MUTUAL_AFFECTION_EXPRESSION, RelationshipEventCategory.RELATIONSHIP, 5.0, 6.0, requires_self_actor=False),
        rr(RelationshipEventType.POSSIBLE_RELATIONSHIP_CONFIRMED, RelationshipEventCategory.RELATIONSHIP, 0.0, 2.0, requires_self_actor=False),
        rr(RelationshipEventType.RELATIONSHIP_CONFIRMED, RelationshipEventCategory.RELATIONSHIP, 0.0, 5.0, requires_self_actor=False),
        rr(RelationshipEventType.FRIEND_ONLY_EXPRESSION, RelationshipEventCategory.RETREAT, -8.0, -6.0, max_per_day=1),
        rr(RelationshipEventType.WITHDRAW_AFFECTION, RelationshipEventCategory.RETREAT, -5.0, -5.0, max_per_day=1),
        rr(RelationshipEventType.STOP_PURSUIT, RelationshipEventCategory.RETREAT, -10.0, -10.0, max_per_day=1),
        rr(RelationshipEventType.RELATIONSHIP_ENDED, RelationshipEventCategory.RETREAT, 0.0, -15.0, max_per_day=1, requires_self_actor=False),
    ]
}
