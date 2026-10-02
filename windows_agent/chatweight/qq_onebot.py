"""OneBot 11 personal-QQ bridge: private friend messages into ChatWeight.

This module speaks the public OneBot protocol only. A separately installed and
logged-in gateway (for example NapCat) owns the QQ connection.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import MessageDirection, MessageType, Platform, UnifiedMessage
from .pipeline import RealtimeAnalysisPipeline
from .session import SessionManager


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _numeric_id(value: Any) -> str | None:
    value = str(value) if isinstance(value, (str, int)) else ""
    return value if value.isdigit() and len(value) <= 20 else None


def _plain_text(message: Any) -> str | None:
    if isinstance(message, str):
        # A CQ code represents non-text content. Do not score or send it to AI.
        return message.strip() if "[CQ:" not in message else None
    if isinstance(message, list) and message and all(
        isinstance(segment, dict) and segment.get("type") == "text"
        and isinstance(segment.get("data"), dict) for segment in message
    ):
        return "".join(str(segment["data"].get("text", "")) for segment in message).strip()
    return None


@dataclass(frozen=True, slots=True)
class PrivateFriendEvent:
    self_id: str
    user_id: str
    message_id: str
    nickname: str
    text: str
    time_ms: int
    direction: MessageDirection = MessageDirection.INCOMING

    @classmethod
    def parse(cls, payload: Any) -> PrivateFriendEvent | None:
        if not isinstance(payload, dict):
            return None
        if payload.get("post_type") != "message" or payload.get("message_type") != "private":
            return None
        if payload.get("sub_type") != "friend":
            return None
        self_id = _numeric_id(payload.get("self_id"))
        sender_id = _numeric_id(payload.get("user_id"))
        message_id = payload.get("message_id")
        if not self_id or not sender_id or not isinstance(message_id, (str, int)):
            return None
        direction = MessageDirection.OUTGOING if sender_id == self_id else MessageDirection.INCOMING
        user_id = _numeric_id(payload.get("target_id")) if direction == MessageDirection.OUTGOING else sender_id
        if not user_id or self_id == user_id:
            return None
        text = _plain_text(payload.get("message"))
        if text is None and payload.get("message") is None:
            text = _plain_text(payload.get("raw_message"))
        if not text or len(text) > 4000:
            return None
        sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
        nickname = (
            user_id if direction == MessageDirection.OUTGOING
            else str(sender.get("nickname") or user_id).strip()[:100] or user_id
        )
        timestamp = payload.get("time")
        time_ms = int(timestamp * 1000) if isinstance(timestamp, (int, float)) and timestamp > 0 else int(time.time() * 1000)
        return cls(self_id, user_id, str(message_id), nickname, text, time_ms, direction)


def verify_onebot_signature(body: bytes, header: str | None, secret: str) -> bool:
    """OneBot HTTP POST X-Signature is ``sha1=<HMAC-SHA1>``."""
    if not secret or not header or not header.startswith("sha1="):
        return False
    expected = "sha1=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(expected, header.strip())


def conversation_id(event: PrivateFriendEvent) -> str:
    return f"qq:onebot:conversation:{event.self_id}:{event.user_id}"


def person_id(event: PrivateFriendEvent) -> str:
    return f"qq:onebot:person:{event.self_id}:{event.user_id}"


class QQOneBotIngestor:
    """Persist stable QQ IDs and run the existing session/weight/relationship core."""

    def __init__(self, db: Any) -> None:
        self.db = db
        self.sessions = SessionManager()
        self.pipeline = RealtimeAnalysisPipeline(db)

    def ingest(self, event: PrivateFriendEvent) -> bool:
        return self._store(event, event.direction, event.message_id, event.text, event.time_ms)

    def record_outgoing(
        self, event: PrivateFriendEvent, sent_id: str, text: str,
        time_ms: int | None = None, capture_source: str = "onebot11_private",
    ) -> bool:
        return self._store(
            event, MessageDirection.OUTGOING, sent_id, text,
            time_ms or int(time.time() * 1000), capture_source,
        )

    def _store(
        self, event: PrivateFriendEvent, direction: MessageDirection,
        message_id: str, text: str, at_ms: int,
        capture_source: str = "onebot11_private",
    ) -> bool:
        cid = conversation_id(event)
        pid = person_id(event)
        display_name = event.nickname
        if direction == MessageDirection.OUTGOING:
            existing = self.db.conn.execute("SELECT display_name FROM persons WHERE id=?", (pid,)).fetchone()
            if existing is not None:
                display_name = existing[0]
        self.db.create_person(pid, display_name, at_ms)
        self.db.create_platform_identity(
            f"identity:{_hash(pid)[:24]}", pid, Platform.QQ.value, display_name, at_ms,
            platform_user_id=event.user_id, alias=display_name,
        )
        self.db.create_conversation(
            cid, Platform.QQ.value, pid, at_ms, title=display_name,
            conversation_type="private", platform_conversation_id=event.user_id,
        )
        fingerprint = _hash("\x1f".join((event.self_id, event.user_id, direction.value, str(message_id))))
        message = UnifiedMessage(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"chatweight:onebot11:{fingerprint}")),
            platform=Platform.QQ, account_id=f"qq:onebot:{event.self_id}",
            conversation_id=cid, person_id=pid,
            sender_id=event.user_id if direction == MessageDirection.INCOMING else event.self_id,
            sender_name=display_name if direction == MessageDirection.INCOMING else "我",
            direction=direction, message_type=MessageType.TEXT, text=text,
            message_time=at_ms, captured_at=at_ms, fingerprint=fingerprint,
            capture_source=capture_source, confidence=1.0,
            raw_json=json.dumps({"onebot_message_id": str(message_id)}, ensure_ascii=False),
        )
        if not self.db.insert_message(message):
            return False
        if cid not in self.sessions.current:
            restored = self.db.load_recent_session(cid, at_ms)
            if restored is not None:
                self.sessions.current[cid] = restored
        session, is_new_session = self.sessions.ingest(message)
        if session.person_id is None:
            session.person_id = pid
        self.db.upsert_session(session)
        self.pipeline.process(message, session, is_new_session)
        return True


class OneBotApiClient:
    """Send only private plain text via an explicitly configured local gateway."""

    def __init__(self, base_url: str, access_token: str, timeout_s: float = 10.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("OneBot API must be a local HTTP endpoint")
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout_s = timeout_s

    def send_private_text(self, user_id: str, text: str) -> str:
        if not self.access_token:
            raise ValueError("OneBot API access token is required for sending")
        numeric_user_id = _numeric_id(user_id)
        if not numeric_user_id or not text.strip():
            raise ValueError("A valid user ID and nonempty text are required")
        body = json.dumps({"user_id": int(numeric_user_id), "message": text, "auto_escape": True},
                          ensure_ascii=False).encode("utf-8")
        request = Request(
            self.base_url + "/send_private_msg", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.access_token}"},
        )
        with urlopen(request, timeout=self.timeout_s) as response:
            result = json.load(response)
        if not isinstance(result, dict) or result.get("status") != "ok":
            raise RuntimeError("OneBot send_private_msg failed")
        message_id = result.get("data", {}).get("message_id") if isinstance(result.get("data"), dict) else None
        if message_id is None:
            raise RuntimeError("OneBot response omitted message_id")
        return str(message_id)

    def get_self_id(self) -> str:
        """Verify which QQ account the local API endpoint controls."""
        if not self.access_token:
            raise ValueError("OneBot API access token is required")
        request = Request(
            self.base_url + "/get_login_info",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        with urlopen(request, timeout=self.timeout_s) as response:
            result = json.load(response)
        if not isinstance(result, dict) or result.get("status") != "ok" or not isinstance(result.get("data"), dict):
            raise RuntimeError("OneBot get_login_info failed")
        self_id = _numeric_id(result["data"].get("user_id"))
        if not self_id:
            raise RuntimeError("OneBot get_login_info omitted user_id")
        return self_id
