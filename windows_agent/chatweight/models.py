from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Platform(str, Enum):
    WECHAT = "wechat"
    QQ = "qq"


class MessageDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    SYSTEM = "system"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    STICKER = "sticker"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"
    LINK = "link"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class ActorSide(str, Enum):
    SELF = "self"
    OTHER = "other"
    BOTH = "both"


class WeightDimension(str, Enum):
    INITIATIVE = "initiative"
    RESPONSE = "response"
    EFFORT = "effort"
    CONTINUITY = "continuity"
    FREQUENCY = "frequency"


class WeightEventType(str, Enum):
    SESSION_START = "session_start"
    FOLLOW_UP_WITHOUT_REPLY = "follow_up_without_reply"
    DIRECT_MENTION = "direct_mention"
    DIRECT_QUOTE = "direct_quote"
    GROUP_GENERAL_MESSAGE = "group_general_message"

    REPLY_WITHIN_1M = "reply_within_1m"
    REPLY_WITHIN_5M = "reply_within_5m"
    REPLY_WITHIN_15M = "reply_within_15m"
    REPLY_WITHIN_60M = "reply_within_60m"
    REPLY_WITHIN_6H = "reply_within_6h"
    DIRECT_REPLY = "direct_reply"
    QUESTION_UNANSWERED_24H = "question_unanswered_24h"
    MULTIPLE_QUESTIONS_UNANSWERED = "multiple_questions_unanswered"

    LONG_REPLY_1_5X = "long_reply_1_5x"
    LONG_REPLY_3X = "long_reply_3x"
    LONG_REPLY_6X = "long_reply_6x"
    BURST_2_3 = "burst_2_3"
    BURST_4_PLUS = "burst_4_plus"
    SEND_IMAGE = "send_image"
    SEND_STICKER = "send_sticker"
    SEND_LINK = "send_link"
    SEND_FILE = "send_file"
    SEND_VOICE_10_30S = "send_voice_10_30s"
    SEND_VOICE_30_60S = "send_voice_30_60s"
    SEND_VOICE_60S_PLUS = "send_voice_60s_plus"
    SHORT_REPLY_CHAIN_3 = "short_reply_chain_3"
    SHORT_REPLY_CHAIN_5 = "short_reply_chain_5"

    SESSION_4_TURNS = "session_4_turns"
    SESSION_8_TURNS = "session_8_turns"
    SESSION_15_TURNS = "session_15_turns"
    SESSION_30_TURNS = "session_30_turns"
    SESSION_20_MIN = "session_20_min"
    SESSION_60_MIN = "session_60_min"
    SESSION_120_MIN = "session_120_min"

    ACTIVE_DAY = "active_day"
    ACTIVE_STREAK_3D = "active_streak_3d"
    ACTIVE_STREAK_7D = "active_streak_7d"
    ACTIVE_STREAK_14D = "active_streak_14d"
    ACTIVE_3_DAYS_WEEK = "active_3_days_week"
    ACTIVE_5_DAYS_WEEK = "active_5_days_week"


class RelationshipType(str, Enum):
    FRIEND = "friend"
    CRUSH = "crush"
    PARTNER = "partner"
    FAMILY = "family"
    COLLEAGUE = "colleague"
    CUSTOM = "custom"


class ExpressionStage(int, Enum):
    NORMAL_CONTACT = 0
    FAMILIARITY = 1
    APPROACHING = 2
    OBVIOUS_CARE = 3
    LIGHT_AFFECTION = 4
    DIRECT_EXPRESSION = 5
    RELATIONSHIP_CONFIRMED = 6


class RelationshipEventCategory(str, Enum):
    FAMILIARITY = "familiarity"
    APPROACH = "approach"
    CARE = "care"
    AFFECTION = "affection"
    DIRECT_EXPRESSION = "direct_expression"
    RELATIONSHIP = "relationship"
    RETREAT = "retreat"


class RelationshipEventType(str, Enum):
    PERSONAL_TOPIC = "personal_topic"
    PERSONAL_QUESTION = "personal_question"
    SELF_DISCLOSURE = "self_disclosure"
    SHARED_EXPERIENCE = "shared_experience"

    INITIATE_PRIVATE_CHAT = "initiate_private_chat"
    TARGETED_SHARING = "targeted_sharing"
    CONTINUE_CONVERSATION = "continue_conversation"
    INITIATE_VOICE_CALL = "initiate_voice_call"
    INITIATE_ACTIVITY = "initiate_activity"
    INITIATE_MEETUP = "initiate_meetup"

    CHECK_IN = "check_in"
    REMEMBER_AND_FOLLOW_UP = "remember_and_follow_up"
    EMOTIONAL_SUPPORT = "emotional_support"
    PRACTICAL_SUPPORT = "practical_support"
    SAFETY_CONCERN = "safety_concern"
    SPECIAL_DATE_ATTENTION = "special_date_attention"

    SPECIAL_COMPLIMENT = "special_compliment"
    SPECIAL_NICKNAME = "special_nickname"
    LIGHT_FLIRT = "light_flirt"
    LIGHT_MISSING_EXPRESSION = "light_missing_expression"
    CARE_EXPRESSION = "care_expression"
    DEPENDENCY_EXPRESSION = "dependency_expression"
    SPECIAL_IMPORTANCE_EXPRESSION = "special_importance_expression"

    DIRECT_LIKE_EXPRESSION = "direct_like_expression"
    DIRECT_ROMANTIC_INTENT = "direct_romantic_intent"
    PURSUIT_EXPRESSION = "pursuit_expression"

    MUTUAL_AFFECTION_EXPRESSION = "mutual_affection_expression"
    POSSIBLE_RELATIONSHIP_CONFIRMED = "possible_relationship_confirmed"
    RELATIONSHIP_CONFIRMED = "relationship_confirmed"

    FRIEND_ONLY_EXPRESSION = "friend_only_expression"
    WITHDRAW_AFFECTION = "withdraw_affection"
    STOP_PURSUIT = "stop_pursuit"
    RELATIONSHIP_ENDED = "relationship_ended"


class DetectionSource(str, Enum):
    LOCAL_FACT = "local_fact"
    LOCAL_SEMANTIC_RULE = "local_semantic_rule"
    SEMANTIC_MODEL = "semantic_model"
    MANUAL = "manual"


class ConfirmationPolicy(str, Enum):
    AUTO_APPLY = "auto_apply"
    HIGH_CONFIDENCE_ONLY = "high_confidence_only"
    USER_REVIEW = "user_review"
    MANUAL_ONLY = "manual_only"


class CandidateStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    AUTO_CONFIRMED = "auto_confirmed"


@dataclass(slots=True)
class UnifiedMessage:
    id: str
    platform: Platform
    conversation_id: str
    direction: MessageDirection
    message_type: MessageType
    message_time: int
    captured_at: int
    fingerprint: str
    account_id: Optional[str] = None
    person_id: Optional[str] = None
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    text: Optional[str] = None
    voice_duration_ms: Optional[int] = None
    reply_to_message_id: Optional[str] = None
    capture_source: str = "adapter"
    confidence: float = 1.0
    raw_json: Optional[str] = None

    @property
    def actor_side(self) -> ActorSide:
        if self.direction == MessageDirection.OUTGOING:
            return ActorSide.SELF
        if self.direction == MessageDirection.INCOMING:
            return ActorSide.OTHER
        return ActorSide.BOTH


@dataclass(slots=True)
class ChatSession:
    id: str
    conversation_id: str
    started_at: int
    last_message_at: int
    initiator_side: ActorSide
    person_id: Optional[str] = None
    ended_at: Optional[int] = None
    message_count: int = 0
    incoming_count: int = 0
    outgoing_count: int = 0
    turn_count: int = 0
    last_actor_side: Optional[ActorSide] = None

    @property
    def duration_ms(self) -> int:
        return max(0, self.last_message_at - self.started_at)


@dataclass(slots=True)
class DetectedWeightEvent:
    id: str
    person_id: str
    conversation_id: str
    actor: ActorSide
    event_type: WeightEventType
    event_time: int
    session_id: Optional[str] = None
    source_message_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RelationshipEventCandidate:
    id: str
    person_id: str
    conversation_id: str
    actor_side: ActorSide
    event_type: RelationshipEventType
    source: DetectionSource
    confidence: float
    confirmation_policy: ConfirmationPolicy
    status: CandidateStatus
    event_time: int
    session_id: Optional[str] = None
    source_message_ids: list[str] = field(default_factory=list)
    evidence_text: Optional[str] = None
    reason_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RelationshipProfileState:
    person_id: str
    relationship_type: RelationshipType = RelationshipType.FRIEND
    custom_label: Optional[str] = None
    expression_stage: ExpressionStage = ExpressionStage.NORMAL_CONTACT
    highest_expression_stage: ExpressionStage = ExpressionStage.NORMAL_CONTACT
    expression_raw: float = 0.0
    expression_heat_raw: float = 0.0
    heat_updated_at: int = 0
    manually_confirmed_stage: Optional[ExpressionStage] = None
    last_relationship_event_at: Optional[int] = None
    updated_at: int = 0

@dataclass(slots=True)
class DimensionWeightState:
    person_id: str
    actor: ActorSide
    dimension: WeightDimension
    recent_raw: float = 0.0
    base_raw: float = 0.0
    updated_at: int = 0
