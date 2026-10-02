from __future__ import annotations

import json
import math
import uuid
from dataclasses import replace
from datetime import datetime

from .detectors import DetectionContext, RelationshipEventDetector
from .engines import RelationshipEngine, RelationshipHeatEngine, score_from_raw
from .models import (
    ActorSide, CandidateStatus, ConfirmationPolicy, DimensionWeightState,
    ExpressionStage, RelationshipEventCategory, RelationshipEventType,
    RelationshipProfileState, RelationshipType, UnifiedMessage, WeightDimension,
)
from .rules import RELATIONSHIP_RULES, WEIGHT_RULES
from .weight import WeightEngine, WeightEventDetector


HIGH_CONFIDENCE_THRESHOLD = 0.80
SIDE_WEIGHTS = {
    WeightDimension.INITIATIVE: 0.25,
    WeightDimension.RESPONSE: 0.25,
    WeightDimension.EFFORT: 0.20,
    WeightDimension.CONTINUITY: 0.20,
    WeightDimension.FREQUENCY: 0.10,
}


def _date_key(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


class RealtimeAnalysisPipeline:
    """Persisted message -> weight + relationship analysis pipeline.

    The capture layer only emits UnifiedMessage. This class owns all derived state.
    """

    def __init__(self, db) -> None:
        self.db = db
        self.weight_detector = WeightEventDetector()
        self.relationship_detector = RelationshipEventDetector()

    def process(self, message: UnifiedMessage, session, is_new_session: bool) -> None:
        if not message.person_id:
            return
        previous = self.db.previous_message(message.conversation_id, message.id)
        recent = self.db.messages_before(message.conversation_id, message.message_time, limit=8)
        median_len = self.db.median_text_length(message.person_id, days=30, now_ms=message.message_time)

        for event in self.weight_detector.detect(
            message, previous, session, is_new_session,
            median_message_length=median_len,
            recent_messages=recent,
        ):
            self._apply_weight_event(event)

        ctx = DetectionContext(
            current=message,
            previous_messages=recent,
            session=session,
            special_nicknames=self.db.special_nicknames(message.person_id),
        )
        for candidate in self.relationship_detector.detect(ctx):
            self._handle_relationship_candidate(candidate)

        self.db.update_daily_metrics(message, session, is_new_session, previous)
        self._apply_frequency_events(message, session)
        self.write_snapshots(message.person_id, message.message_time)

    def _apply_weight_event(self, event) -> None:
        rule = WEIGHT_RULES[event.event_type]
        if self.db.weight_event_exists(event.id, event.event_type.value, event.source_message_ids):
            return
        if event.session_id and (not rule.repeatable):
            if self.db.count_weight_event_in_session(event.session_id, event.person_id, event.actor.value, event.event_type.value) >= 1:
                return
        if rule.max_per_session is not None and event.session_id:
            if self.db.count_weight_event_in_session(event.session_id, event.person_id, event.actor.value, event.event_type.value) >= rule.max_per_session:
                return
        occurrence = 1
        if rule.repeat_group and event.session_id:
            occurrence += self.db.count_weight_repeat_group(
                event.session_id, event.person_id, event.actor.value, rule.repeat_group
            )
        positive_used, negative_used = self.db.daily_weight_usage(
            event.person_id, event.actor.value, rule.dimension.value, _date_key(event.event_time)
        )
        state = self.db.get_weight_state(event.person_id, event.actor, rule.dimension)
        new_state, delta = WeightEngine.apply(
            state, event, occurrence=occurrence,
            positive_used_today=positive_used,
            negative_used_today=negative_used,
        )
        if abs(delta) < 1e-12:
            return
        self.db.insert_weight_event(event, rule, occurrence, delta)
        self.db.upsert_weight_state(new_state)

    def _apply_frequency_events(self, message, session) -> None:
        from .models import DetectedWeightEvent, WeightEventType
        day = _date_key(message.message_time)
        active_days = self.db.active_dates(message.person_id, message.message_time, days=21)
        events = [WeightEventType.ACTIVE_DAY]
        streak = 0
        cursor = datetime.strptime(day, "%Y-%m-%d").date()
        dates = set(active_days)
        from datetime import timedelta
        while cursor.isoformat() in dates:
            streak += 1
            cursor -= timedelta(days=1)
        if streak >= 14: events.append(WeightEventType.ACTIVE_STREAK_14D)
        elif streak >= 7: events.append(WeightEventType.ACTIVE_STREAK_7D)
        elif streak >= 3: events.append(WeightEventType.ACTIVE_STREAK_3D)
        week_dates = [d for d in active_days if d >= (datetime.strptime(day, "%Y-%m-%d").date() - timedelta(days=6)).isoformat()]
        if len(set(week_dates)) >= 5: events.append(WeightEventType.ACTIVE_5_DAYS_WEEK)
        elif len(set(week_dates)) >= 3: events.append(WeightEventType.ACTIVE_3_DAYS_WEEK)
        for et in events:
            eid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"freq:{message.person_id}:{message.actor_side.value}:{day}:{et.value}"))
            ev = DetectedWeightEvent(eid, message.person_id, message.conversation_id, message.actor_side, et, message.message_time, session.id, [message.id], 1.0)
            self._apply_weight_event(ev)

    def _handle_relationship_candidate(self, candidate) -> None:
        # Never let candidates for unknown pseudo-persons mutate a real profile.
        if candidate.person_id == "unknown":
            return
        status = CandidateStatus.PENDING
        auto_apply = False
        if candidate.confirmation_policy == ConfirmationPolicy.AUTO_APPLY:
            auto_apply = True
        elif candidate.confirmation_policy == ConfirmationPolicy.HIGH_CONFIDENCE_ONLY:
            if candidate.confidence >= HIGH_CONFIDENCE_THRESHOLD:
                auto_apply = True
        candidate = replace(candidate, status=status)
        if not self.db.insert_relationship_candidate(candidate):
            return
        if auto_apply:
            self.confirm_candidate(candidate.id, automatic=True)

    def confirm_candidate(self, candidate_id: str, automatic: bool = False) -> bool:
        candidate = self.db.load_relationship_candidate(candidate_id)
        if candidate is None:
            return False
        if candidate.status in (CandidateStatus.CONFIRMED, CandidateStatus.AUTO_CONFIRMED):
            return True
        if candidate.status == CandidateStatus.REJECTED:
            return False

        # Manual-only items can only be confirmed by an explicit caller.
        if automatic and candidate.confirmation_policy == ConfirmationPolicy.MANUAL_ONLY:
            return False

        final_status = CandidateStatus.AUTO_CONFIRMED if automatic else CandidateStatus.CONFIRMED
        candidate = replace(candidate, status=final_status)
        self.db.update_candidate_status(candidate.id, final_status.value)

        rule = RELATIONSHIP_RULES[candidate.event_type]
        if rule.max_per_session is not None and candidate.session_id:
            if self.db.count_relationship_event_in_session(candidate.session_id, candidate.person_id, candidate.event_type.value) >= rule.max_per_session:
                return True
        if rule.max_per_day is not None:
            if self.db.count_relationship_event_on_date(candidate.person_id, candidate.event_type.value, _date_key(candidate.event_time)) >= rule.max_per_day:
                return True
        repeat_mult = 1.0
        if rule.repeat_group and candidate.session_id:
            count = self.db.count_relationship_repeat_group(candidate.session_id, candidate.person_id, rule.repeat_group)
            repeat_mult = 1.0 if count == 0 else 0.7 if count == 1 else 0.5 if count == 2 else 0.3

        profile = self.db.get_relationship_profile(candidate.person_id, candidate.event_time)
        # Relationship expression stage is meaningful only when the user marks the person as CRUSH/PARTNER.
        # We still store the event for FRIEND etc., but do not mutate expression progression.
        should_apply_expression = profile.relationship_type in (RelationshipType.CRUSH, RelationshipType.PARTNER)
        evidence = self.db.build_relationship_evidence(candidate.person_id, candidate.event_time, include_candidate=candidate)
        updated = profile
        if should_apply_expression:
            updated = RelationshipEngine.apply(profile, candidate, evidence, repeat_mult=repeat_mult)
        self.db.insert_relationship_event(candidate, rule, repeat_mult)
        if should_apply_expression:
            self.db.upsert_relationship_profile(updated, candidate.event_time)
        return True

    def reject_candidate(self, candidate_id: str) -> bool:
        return self.db.update_candidate_status(candidate_id, CandidateStatus.REJECTED.value)

    def write_snapshots(self, person_id: str, now_ms: int) -> None:
        local_date = _date_key(now_ms)
        for side in (ActorSide.SELF, ActorSide.OTHER):
            scores = {}
            recent_total = base_total = 0.0
            for dim in WeightDimension:
                state = self.db.get_weight_state(person_id, side, dim)
                # Read-time decay avoids needing a background timer.
                elapsed = max(0, now_ms - state.updated_at) / 86_400_000 if state.updated_at else 0.0
                from .engines import RECENT_HALF_LIFE_DAYS, BASE_HALF_LIFE_DAYS, decay
                recent = decay(state.recent_raw, elapsed, RECENT_HALF_LIFE_DAYS[dim])
                base = decay(state.base_raw, elapsed, BASE_HALF_LIFE_DAYS)
                raw = recent * 0.75 + base * 0.25
                scores[dim] = score_from_raw(raw)
                recent_total += recent
                base_total += base
            overall = sum(scores[d] * SIDE_WEIGHTS[d] for d in WeightDimension)
            self.db.upsert_daily_weight_snapshot(person_id, local_date, side, scores, overall, recent_total, base_total, now_ms)

        profile = self.db.get_relationship_profile(person_id, now_ms)
        heat_raw = RelationshipHeatEngine.decay(profile.expression_heat_raw, profile.heat_updated_at or now_ms, now_ms)
        counts = self.db.relationship_category_counts(person_id, local_date)
        self.db.upsert_relationship_daily_snapshot(
            profile, local_date, heat_raw, RelationshipHeatEngine.to_score(heat_raw), counts,
            self.db.valid_session_count(person_id, local_date), now_ms,
        )
