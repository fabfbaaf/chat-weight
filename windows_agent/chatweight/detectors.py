from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from .models import (
    ActorSide,
    CandidateStatus,
    ChatSession,
    ConfirmationPolicy,
    DetectionSource,
    MessageDirection,
    MessageType,
    RelationshipEventCandidate,
    RelationshipEventType,
    UnifiedMessage,
)

SESSION_GAP_MS = 30 * 60 * 1000


@dataclass(slots=True)
class DetectionContext:
    current: UnifiedMessage
    previous_messages: list[UnifiedMessage]
    session: ChatSession | None
    special_nicknames: set[str]


def _candidate(ctx: DetectionContext, event_type: RelationshipEventType, source: DetectionSource,
               confidence: float, policy: ConfirmationPolicy, reason: str, evidence: str | None = None) -> RelationshipEventCandidate:
    return RelationshipEventCandidate(
        id=str(uuid.uuid4()),
        person_id=ctx.current.person_id or "unknown",
        conversation_id=ctx.current.conversation_id,
        session_id=ctx.session.id if ctx.session else None,
        actor_side=ctx.current.actor_side,
        event_type=event_type,
        source=source,
        confidence=confidence,
        confirmation_policy=policy,
        status=CandidateStatus.AUTO_CONFIRMED if policy == ConfirmationPolicy.AUTO_APPLY else CandidateStatus.PENDING,
        event_time=ctx.current.message_time,
        source_message_ids=[ctx.current.id],
        evidence_text=evidence or ctx.current.text,
        reason_code=reason,
    )


class LocalBehaviorDetector:
    def detect(self, ctx: DetectionContext) -> list[RelationshipEventCandidate]:
        out: list[RelationshipEventCandidate] = []
        cur = ctx.current
        if cur.direction not in (MessageDirection.OUTGOING, MessageDirection.INCOMING):
            return out

        is_session_start = not ctx.previous_messages or (cur.message_time - ctx.previous_messages[-1].message_time) >= SESSION_GAP_MS
        if is_session_start:
            out.append(_candidate(
                ctx,
                RelationshipEventType.INITIATE_PRIVATE_CHAT,
                DetectionSource.LOCAL_FACT,
                1.0,
                ConfirmationPolicy.AUTO_APPLY,
                "session_start_by_actor",
            ))

        if cur.message_type in (MessageType.IMAGE, MessageType.VIDEO, MessageType.LINK):
            prev = ctx.previous_messages[-1] if ctx.previous_messages else None
            requested = bool(prev and prev.text and re.search(r"(发(我|一下)|给我|看看|链接|照片|图片|视频)", prev.text))
            if not requested:
                out.append(_candidate(
                    ctx,
                    RelationshipEventType.TARGETED_SHARING,
                    DetectionSource.LOCAL_FACT,
                    0.82,
                    ConfirmationPolicy.HIGH_CONFIDENCE_ONLY,
                    "unsolicited_media_or_link_share",
                ))
        return out


class LocalPhraseDetector:
    NEGATION = ("不想你", "没想你", "才不想", "谁想你")
    CHECK_IN = re.compile(r"(你.*(怎么样|还好吗|好点了吗|累不累|到家了吗|吃了吗|睡了吗)|到家了没|还难受吗)")
    MISSING = re.compile(r"((有点|突然|挺|很|好)?想(你|你了)|想念你|老想到你)")
    DIRECT_LIKE = re.compile(r"(我(真的|其实|挺|很)?喜欢你|我对你.*(有感觉|不是普通朋友)|我想追你)")
    FRIEND_ONLY = re.compile(r"(只把你当朋友|我们还是做朋友吧|就做朋友吧)")
    RELATION_CONFIRMED = re.compile(r"(我们在一起吧|那我们算.*(情侣|在一起)|你就是我(女朋友|男朋友))")
    RELATION_ENDED = re.compile(r"(分手吧|我们分手|以后别联系了|到这里吧)")

    def detect(self, ctx: DetectionContext) -> list[RelationshipEventCandidate]:
        text = (ctx.current.text or "").strip()
        if not text:
            return []

        out: list[RelationshipEventCandidate] = []
        if self.CHECK_IN.search(text):
            out.append(_candidate(ctx, RelationshipEventType.CHECK_IN, DetectionSource.LOCAL_SEMANTIC_RULE,
                                  0.86, ConfirmationPolicy.HIGH_CONFIDENCE_ONLY, "check_in_phrase", text))

        if self.MISSING.search(text) and not any(x in text for x in self.NEGATION):
            out.append(_candidate(ctx, RelationshipEventType.LIGHT_MISSING_EXPRESSION,
                                  DetectionSource.LOCAL_SEMANTIC_RULE, 0.91,
                                  ConfirmationPolicy.HIGH_CONFIDENCE_ONLY, "explicit_missing_phrase", text))

        if any(n and n in text for n in ctx.special_nicknames):
            out.append(_candidate(ctx, RelationshipEventType.SPECIAL_NICKNAME,
                                  DetectionSource.LOCAL_SEMANTIC_RULE, 0.98,
                                  ConfirmationPolicy.AUTO_APPLY, "configured_special_nickname", text))

        if self.DIRECT_LIKE.search(text):
            et = RelationshipEventType.PURSUIT_EXPRESSION if "追你" in text else RelationshipEventType.DIRECT_LIKE_EXPRESSION
            out.append(_candidate(ctx, et, DetectionSource.LOCAL_SEMANTIC_RULE, 0.98,
                                  ConfirmationPolicy.USER_REVIEW, "explicit_romantic_phrase", text))

        if self.FRIEND_ONLY.search(text):
            out.append(_candidate(ctx, RelationshipEventType.FRIEND_ONLY_EXPRESSION,
                                  DetectionSource.LOCAL_SEMANTIC_RULE, 0.96,
                                  ConfirmationPolicy.USER_REVIEW, "friend_only_phrase", text))

        if self.RELATION_CONFIRMED.search(text):
            out.append(_candidate(ctx, RelationshipEventType.POSSIBLE_RELATIONSHIP_CONFIRMED,
                                  DetectionSource.LOCAL_SEMANTIC_RULE, 0.90,
                                  ConfirmationPolicy.MANUAL_ONLY, "relationship_confirmation_phrase", text))

        if self.RELATION_ENDED.search(text):
            out.append(_candidate(ctx, RelationshipEventType.RELATIONSHIP_ENDED,
                                  DetectionSource.LOCAL_SEMANTIC_RULE, 0.90,
                                  ConfirmationPolicy.MANUAL_ONLY, "relationship_end_phrase", text))
        return out


SUPPRESSES: dict[RelationshipEventType, set[RelationshipEventType]] = {
    RelationshipEventType.LIGHT_MISSING_EXPRESSION: {RelationshipEventType.SELF_DISCLOSURE},
    RelationshipEventType.DIRECT_LIKE_EXPRESSION: {
        RelationshipEventType.LIGHT_FLIRT,
        RelationshipEventType.SPECIAL_IMPORTANCE_EXPRESSION,
    },
    RelationshipEventType.PURSUIT_EXPRESSION: {RelationshipEventType.LIGHT_FLIRT},
    RelationshipEventType.REMEMBER_AND_FOLLOW_UP: {RelationshipEventType.CHECK_IN},
}


class RelationshipEventDetector:
    def __init__(self) -> None:
        self._detectors = [LocalBehaviorDetector(), LocalPhraseDetector()]

    def detect(self, ctx: DetectionContext) -> list[RelationshipEventCandidate]:
        items: list[RelationshipEventCandidate] = []
        for detector in self._detectors:
            items.extend(detector.detect(ctx))
        return self._merge_and_dedupe(items)

    @staticmethod
    def _merge_and_dedupe(items: list[RelationshipEventCandidate]) -> list[RelationshipEventCandidate]:
        best: dict[RelationshipEventType, RelationshipEventCandidate] = {}
        for item in items:
            prev = best.get(item.event_type)
            if prev is None or item.confidence > prev.confidence:
                best[item.event_type] = item

        active = set(best)
        for high, lows in SUPPRESSES.items():
            if high in active:
                for low in lows:
                    best.pop(low, None)
        return sorted(best.values(), key=lambda x: x.event_type.value)
