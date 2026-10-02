from __future__ import annotations

import time
import uuid

from .detectors import DetectionContext, RelationshipEventDetector
from .engines import RelationshipEngine, RelationshipHeatEngine
from .models import (
    CandidateStatus,
    MessageDirection,
    MessageType,
    Platform,
    RelationshipProfileState,
    RelationshipType,
    UnifiedMessage,
)
from .rules import RELATIONSHIP_RULES
from .session import SessionManager


def message(text: str, outgoing: bool, ts: int, idx: int) -> UnifiedMessage:
    return UnifiedMessage(
        id=f"m{idx}",
        platform=Platform.WECHAT,
        conversation_id="wechat:xiaoyu",
        person_id="person:xiaoyu",
        direction=MessageDirection.OUTGOING if outgoing else MessageDirection.INCOMING,
        message_type=MessageType.TEXT,
        text=text,
        message_time=ts,
        captured_at=ts,
        fingerprint=f"fp:{idx}",
    )


def run() -> None:
    base = int(time.time() * 1000)
    msgs = [
        message("早呀，今天怎么样？", True, base, 1),
        message("还好，下午还有个汇报", False, base + 60_000, 2),
        message("你之前不是说这次准备挺久吗，别紧张", True, base + 120_000, 3),
        message("哈哈谢谢", False, base + 180_000, 4),
        message("突然有点想你了", True, base + 240_000, 5),
        message("其实我挺喜欢你的", True, base + 300_000, 6),
    ]

    session_mgr = SessionManager()
    detector = RelationshipEventDetector()
    profile = RelationshipProfileState(
        person_id="person:xiaoyu",
        relationship_type=RelationshipType.CRUSH,
        heat_updated_at=base,
        updated_at=base,
    )

    history: list[UnifiedMessage] = []
    print("ChatWeight V1 demo\n")
    for msg in msgs:
        session, _ = session_mgr.ingest(msg)
        candidates = detector.detect(DetectionContext(msg, history[-5:], session, {"小朋友"}))
        print(f"{msg.direction.value:8} {msg.text}")
        for c in candidates:
            print(f"  candidate: {c.event_type.value}  confidence={c.confidence:.2f}  policy={c.confirmation_policy.value}")
            if c.status == CandidateStatus.AUTO_CONFIRMED or c.confirmation_policy.value == "high_confidence_only" and c.confidence >= 0.80:
                evidence = {
                    "valid_sessions_30d": 4,
                    "approach_event_count_14d": 4,
                    "distinct_care_event_types_30d": 2,
                    "has_affection_event": c.event_type.value in {"light_missing_expression", "light_flirt", "special_importance_expression"},
                    "has_direct_expression_event": False,
                    "relationship_confirmed": False,
                }
                profile = RelationshipEngine.apply(profile, c, evidence)
            elif c.confirmation_policy.value in {"user_review", "manual_only"}:
                print("  -> waiting for user confirmation; not applied")
        history.append(msg)

    print("\nCurrent profile")
    print(" stage:", profile.expression_stage.name)
    print(" raw:", round(profile.expression_raw, 2))
    print(" heat:", round(RelationshipHeatEngine.to_score(profile.expression_heat_raw), 2))
    print(" highest:", profile.highest_expression_stage.name)


if __name__ == "__main__":
    run()
