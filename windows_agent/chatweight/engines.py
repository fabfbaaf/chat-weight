from __future__ import annotations

import math
from dataclasses import replace

from .models import (
    ActorSide,
    ExpressionStage,
    RelationshipEventCandidate,
    RelationshipEventCategory,
    RelationshipEventType,
    RelationshipProfileState,
    WeightDimension,
)
from .rules import RELATIONSHIP_RULES


RECENT_HALF_LIFE_DAYS = {
    WeightDimension.INITIATIVE: 30.0,
    WeightDimension.RESPONSE: 14.0,
    WeightDimension.EFFORT: 30.0,
    WeightDimension.CONTINUITY: 30.0,
    WeightDimension.FREQUENCY: 14.0,
}
BASE_HALF_LIFE_DAYS = 180.0
SCORE_K = 20.0


def decay(value: float, elapsed_days: float, half_life_days: float) -> float:
    if elapsed_days <= 0:
        return value
    return value * math.pow(2.0, -elapsed_days / half_life_days)


def score_from_raw(raw: float, k: float = SCORE_K) -> float:
    x = max(raw, 0.0)
    return 100.0 * (1.0 - math.exp(-x / k))


def repeat_multiplier(occurrence: int) -> float:
    if occurrence <= 1:
        return 1.0
    if occurrence == 2:
        return 0.7
    if occurrence == 3:
        return 0.5
    return 0.3


def mutuality(self_score: float, other_score: float) -> float:
    balance = 1.0 - abs(self_score - other_score) / (self_score + other_score + 1.0)
    return ((self_score + other_score) / 2.0) * balance


class RelationshipHeatEngine:
    HALF_LIFE_DAYS = 14.0
    SCORE_K = 12.0

    @classmethod
    def decay(cls, raw: float, from_ms: int, to_ms: int) -> float:
        if to_ms <= from_ms:
            return raw
        days = (to_ms - from_ms) / 86_400_000.0
        return decay(raw, days, cls.HALF_LIFE_DAYS)

    @classmethod
    def to_score(cls, raw: float) -> float:
        return score_from_raw(raw, cls.SCORE_K)


class RelationshipStageEvaluator:
    @staticmethod
    def evaluate(profile: RelationshipProfileState, evidence: dict[str, object]) -> ExpressionStage:
        if profile.manually_confirmed_stage is not None:
            return profile.manually_confirmed_stage
        if bool(evidence.get("relationship_confirmed", False)):
            return ExpressionStage.RELATIONSHIP_CONFIRMED
        if bool(evidence.get("has_direct_expression_event", False)):
            return ExpressionStage.DIRECT_EXPRESSION

        raw = profile.expression_raw
        if raw >= 60 and bool(evidence.get("has_affection_event", False)):
            return ExpressionStage.LIGHT_AFFECTION
        if raw >= 45 and int(evidence.get("distinct_care_event_types_30d", 0)) >= 2:
            return ExpressionStage.OBVIOUS_CARE
        if raw >= 30 and int(evidence.get("approach_event_count_14d", 0)) >= 3:
            return ExpressionStage.APPROACHING
        if raw >= 15 and int(evidence.get("valid_sessions_30d", 0)) >= 3:
            return ExpressionStage.FAMILIARITY
        return ExpressionStage.NORMAL_CONTACT


class RelationshipEngine:
    """Pure state transition engine. Persistence/limits live in repositories."""

    @staticmethod
    def apply(
        profile: RelationshipProfileState,
        event: RelationshipEventCandidate,
        evidence: dict[str, object],
        repeat_mult: float = 1.0,
    ) -> RelationshipProfileState:
        rule = RELATIONSHIP_RULES[event.event_type]

        if rule.requires_self_actor and event.actor_side != ActorSide.SELF:
            return profile

        confidence = min(max(event.confidence, 0.0), 1.0)
        progress_delta = rule.progress_delta * repeat_mult * confidence
        heat_delta = rule.heat_delta * repeat_mult * confidence

        heat_from = profile.heat_updated_at or event.event_time
        decayed_heat = RelationshipHeatEngine.decay(profile.expression_heat_raw, heat_from, event.event_time)

        updated = replace(
            profile,
            expression_raw=min(max(profile.expression_raw + progress_delta, 0.0), 100.0),
            expression_heat_raw=max(decayed_heat + heat_delta, 0.0),
            heat_updated_at=event.event_time,
            last_relationship_event_at=event.event_time,
            updated_at=event.event_time,
        )

        if rule.category == RelationshipEventCategory.RETREAT:
            updated = replace(updated, expression_stage=RelationshipEngine._retreat_stage(updated.expression_stage, event.event_type))
        else:
            evaluated = RelationshipStageEvaluator.evaluate(updated, evidence)
            updated = replace(updated, expression_stage=max(updated.expression_stage, evaluated, key=lambda s: int(s)))

        updated = replace(
            updated,
            highest_expression_stage=max(updated.highest_expression_stage, updated.expression_stage, key=lambda s: int(s)),
        )
        return updated

    @staticmethod
    def _retreat_stage(current: ExpressionStage, event_type: RelationshipEventType) -> ExpressionStage:
        if event_type == RelationshipEventType.FRIEND_ONLY_EXPRESSION:
            return ExpressionStage.FAMILIARITY
        if event_type == RelationshipEventType.WITHDRAW_AFFECTION:
            return min(current, ExpressionStage.OBVIOUS_CARE, key=lambda s: int(s))
        if event_type == RelationshipEventType.STOP_PURSUIT:
            return ExpressionStage.FAMILIARITY
        if event_type == RelationshipEventType.RELATIONSHIP_ENDED:
            return ExpressionStage.NORMAL_CONTACT
        return current
