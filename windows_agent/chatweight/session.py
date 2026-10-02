from __future__ import annotations

import uuid

from .models import ActorSide, ChatSession, MessageDirection, UnifiedMessage

SESSION_GAP_MS = 30 * 60 * 1000


class SessionManager:
    def __init__(self) -> None:
        self.current: dict[str, ChatSession] = {}

    def ingest(self, message: UnifiedMessage) -> tuple[ChatSession, bool]:
        session = self.current.get(message.conversation_id)
        is_new = session is None or message.message_time - session.last_message_at >= SESSION_GAP_MS
        actor = message.actor_side

        if is_new:
            session = ChatSession(
                id=str(uuid.uuid4()),
                conversation_id=message.conversation_id,
                person_id=message.person_id,
                started_at=message.message_time,
                last_message_at=message.message_time,
                initiator_side=actor,
                message_count=0,
                last_actor_side=None,
            )
            self.current[message.conversation_id] = session

        session.message_count += 1
        if message.direction == MessageDirection.INCOMING:
            session.incoming_count += 1
        elif message.direction == MessageDirection.OUTGOING:
            session.outgoing_count += 1
        if session.last_actor_side is not None and actor != session.last_actor_side and actor != ActorSide.BOTH:
            session.turn_count += 1
        session.last_actor_side = actor
        session.last_message_at = message.message_time
        return session, is_new
