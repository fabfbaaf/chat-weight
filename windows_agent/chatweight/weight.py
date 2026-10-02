from __future__ import annotations

import uuid
from dataclasses import replace

from .engines import BASE_HALF_LIFE_DAYS, RECENT_HALF_LIFE_DAYS, decay, repeat_multiplier
from .models import (
    ActorSide,
    ChatSession,
    DetectedWeightEvent,
    DimensionWeightState,
    MessageDirection,
    MessageType,
    UnifiedMessage,
    WeightDimension,
    WeightEventType,
)
from .rules import WEIGHT_RULES


DAILY_CAPS = {
    WeightDimension.INITIATIVE: (8.0, -4.0),
    WeightDimension.RESPONSE: (8.0, -4.0),
    WeightDimension.EFFORT: (8.0, -4.0),
    WeightDimension.CONTINUITY: (8.0, -4.0),
    WeightDimension.FREQUENCY: (3.0, -2.0),
}


class WeightEventDetector:
    def detect(
        self,
        current: UnifiedMessage,
        previous: UnifiedMessage | None,
        session: ChatSession,
        is_new_session: bool,
        median_message_length: float = 12.0,
        recent_messages: list[UnifiedMessage] | None = None,
    ) -> list[DetectedWeightEvent]:
        if not current.person_id or current.direction == MessageDirection.SYSTEM:
            return []
        out: list[DetectedWeightEvent] = []
        recent_messages = recent_messages or []

        def emit(t: WeightEventType, confidence: float = 1.0) -> None:
            out.append(DetectedWeightEvent(
                id=str(uuid.uuid4()), person_id=current.person_id, conversation_id=current.conversation_id,
                session_id=session.id, actor=current.actor_side, event_type=t, event_time=current.message_time,
                source_message_ids=[current.id], confidence=confidence,
            ))

        if is_new_session:
            emit(WeightEventType.SESSION_START)

        if previous and previous.actor_side != current.actor_side and previous.actor_side != ActorSide.BOTH:
            ms = current.message_time - previous.message_time
            if ms <= 60_000:
                emit(WeightEventType.REPLY_WITHIN_1M)
            elif ms <= 5 * 60_000:
                emit(WeightEventType.REPLY_WITHIN_5M)
            elif ms <= 15 * 60_000:
                emit(WeightEventType.REPLY_WITHIN_15M)
            elif ms <= 60 * 60_000:
                emit(WeightEventType.REPLY_WITHIN_60M)
            elif ms <= 6 * 60 * 60_000:
                emit(WeightEventType.REPLY_WITHIN_6H)


        # Follow-up without reply: same actor speaks again after a pause, still inside the session.
        if previous and previous.actor_side == current.actor_side and previous.actor_side != ActorSide.BOTH:
            gap = current.message_time - previous.message_time
            if 5 * 60_000 <= gap < 30 * 60_000:
                emit(WeightEventType.FOLLOW_UP_WITHOUT_REPLY)

        # Burst: count same-side messages in the previous 90 seconds, including current.
        same_side = [m for m in recent_messages if m.actor_side == current.actor_side and 0 <= current.message_time - m.message_time <= 90_000]
        burst_count = len(same_side) + 1
        if burst_count == 2:
            emit(WeightEventType.BURST_2_3)
        elif burst_count == 4:
            emit(WeightEventType.BURST_4_PLUS)

        # Short-reply chains are behavioral patterns, not a single short message.
        chain = [m for m in recent_messages[-8:] if m.actor_side == current.actor_side and m.text is not None]
        chain.append(current)
        tail = []
        for m in reversed(chain):
            if m.actor_side != current.actor_side or not m.text or len(m.text.strip()) > 6:
                break
            tail.append(m)
        if len(tail) == 3:
            emit(WeightEventType.SHORT_REPLY_CHAIN_3)
        elif len(tail) == 5:
            emit(WeightEventType.SHORT_REPLY_CHAIN_5)

        if current.message_type == MessageType.IMAGE:
            emit(WeightEventType.SEND_IMAGE)
        elif current.message_type == MessageType.STICKER:
            emit(WeightEventType.SEND_STICKER)
        elif current.message_type == MessageType.LINK:
            emit(WeightEventType.SEND_LINK)
        elif current.message_type == MessageType.FILE:
            emit(WeightEventType.SEND_FILE)
        elif current.message_type == MessageType.VOICE and current.voice_duration_ms:
            seconds = current.voice_duration_ms / 1000
            if seconds >= 60:
                emit(WeightEventType.SEND_VOICE_60S_PLUS)
            elif seconds >= 30:
                emit(WeightEventType.SEND_VOICE_30_60S)
            elif seconds >= 10:
                emit(WeightEventType.SEND_VOICE_10_30S)

        if current.text and median_message_length > 0:
            ratio = len(current.text.strip()) / median_message_length
            if ratio >= 6:
                emit(WeightEventType.LONG_REPLY_6X)
            elif ratio >= 3:
                emit(WeightEventType.LONG_REPLY_3X)
            elif ratio >= 1.5:
                emit(WeightEventType.LONG_REPLY_1_5X)

        for threshold, event_type in (
            (30, WeightEventType.SESSION_30_TURNS),
            (15, WeightEventType.SESSION_15_TURNS),
            (8, WeightEventType.SESSION_8_TURNS),
            (4, WeightEventType.SESSION_4_TURNS),
        ):
            if session.turn_count == threshold:
                emit(event_type)
                break

        mins = session.duration_ms / 60_000
        if mins >= 120:
            emit(WeightEventType.SESSION_120_MIN)
        if mins >= 60:
            emit(WeightEventType.SESSION_60_MIN)
        if mins >= 20:
            emit(WeightEventType.SESSION_20_MIN)
        return out


class WeightEngine:
    @staticmethod
    def apply(
        state: DimensionWeightState,
        event: DetectedWeightEvent,
        occurrence: int = 1,
        positive_used_today: float = 0.0,
        negative_used_today: float = 0.0,
    ) -> tuple[DimensionWeightState, float]:
        rule = WEIGHT_RULES[event.event_type]
        multiplier = repeat_multiplier(occurrence) if rule.repeatable else 1.0
        delta = rule.base_delta * multiplier * min(max(event.confidence, 0.0), 1.0)

        pos_cap, neg_cap = DAILY_CAPS[rule.dimension]
        if delta >= 0:
            delta = max(0.0, min(delta, pos_cap - positive_used_today))
        else:
            # negative_used_today is <= 0
            allowed = neg_cap - negative_used_today
            delta = max(delta, allowed)
            delta = min(delta, 0.0)

        elapsed_days = max(0, event.event_time - state.updated_at) / 86_400_000.0 if state.updated_at else 0.0
        recent = decay(state.recent_raw, elapsed_days, RECENT_HALF_LIFE_DAYS[rule.dimension])
        base = decay(state.base_raw, elapsed_days, BASE_HALF_LIFE_DAYS)
        return replace(
            state,
            recent_raw=recent + delta,
            base_raw=base + delta * rule.base_share,
            updated_at=event.event_time,
        ), delta
