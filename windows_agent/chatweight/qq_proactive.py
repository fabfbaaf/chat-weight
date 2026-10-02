"""One-shot proactive QQ check-in after a quiet conversation interval.

Run this periodically (for example with systemd timer). The only send path is
explicitly allowlisted and records an attempt before calling the gateway, so an
uncertain HTTP outcome is never retried automatically.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import ChatWeightDb
from .qq_bot import _default_schema, recent_context, relationship_context
from .qq_onebot import OneBotApiClient, PrivateFriendEvent, QQOneBotIngestor
from .qq_reply import ProactivePlan, QQReplyEngine, is_local_model_url


@dataclass(frozen=True)
class ProactivePolicy:
    idle_hours: float = 12.0
    local_hour_start: int = 10
    local_hour_end: int = 21
    utc_offset_hours: int = 8
    min_confidence: float = 0.85

    def validate(self) -> None:
        if not math.isfinite(self.idle_hours) or self.idle_hours <= 0:
            raise ValueError("idle hours must be positive")
        if not 0 <= self.local_hour_start < self.local_hour_end <= 24:
            raise ValueError("invalid local sending hours")
        if not -12 <= self.utc_offset_hours <= 14:
            raise ValueError("invalid UTC offset")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("invalid confidence threshold")

    def local_datetime(self, now_ms: int) -> datetime:
        zone = timezone(timedelta(hours=self.utc_offset_hours))
        return datetime.fromtimestamp(now_ms / 1000, tz=zone)

    def within_hours(self, now_ms: int) -> bool:
        hour = self.local_datetime(now_ms).hour
        return self.local_hour_start <= hour < self.local_hour_end


@dataclass(frozen=True)
class ProactiveContact:
    self_id: str
    user_id: str
    nickname: str
    conversation_id: str
    last_message_at: int
    last_message_id: str


class ProactiveSuggestionStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, contact: ProactiveContact, plan: ProactivePlan, *, sent: bool, status: str, now_ms: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, ValueError):
            existing = {}
        existing[contact.user_id] = {
            "kind": "proactive",
            "user_id": contact.user_id,
            "nickname": contact.nickname,
            "updated_at": now_ms,
            "judgment": asdict(plan.judgment) if plan.judgment else None,
            "candidates": [asdict(candidate) for candidate in plan.candidates],
            "reason": plan.reason,
            "status": status,
            "auto_sent": sent,
        }
        pending = self.path.with_name(self.path.name + ".tmp")
        pending.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(pending, self.path)


class QQProactiveRunner:
    def __init__(
        self, db: ChatWeightDb, replies: QQReplyEngine, suggestions: ProactiveSuggestionStore,
        *, self_id: str, allowed_user_ids: frozenset[str], policy: ProactivePolicy,
        api: OneBotApiClient | None = None, send: bool = False,
    ) -> None:
        policy.validate()
        if not self_id.isdigit() or not allowed_user_ids or any(not value.isdigit() for value in allowed_user_ids):
            raise ValueError("numeric self ID and at least one allowlisted friend ID are required")
        if send and api is None:
            raise ValueError("sending requires a local OneBot API client")
        self.db = db
        self.replies = replies
        self.suggestions = suggestions
        self.self_id = self_id
        self.allowed_user_ids = allowed_user_ids
        self.policy = policy
        self.api = api
        self.send = send
        self.ingestor = QQOneBotIngestor(db)

    def run_once(self, now_ms: int | None = None) -> dict[str, str]:
        fixed_now = now_ms is not None
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        if not self.policy.within_hours(now_ms):
            return {user_id: "quiet_hours" for user_id in self.allowed_user_ids}
        if self.send:
            assert self.api is not None
            if self.api.get_self_id() != self.self_id:
                raise RuntimeError("NapCat API account differs from the configured QQ self ID")
        outcomes: dict[str, str] = {}
        for user_id in sorted(self.allowed_user_ids):
            contact = self._eligible_contact(user_id, now_ms)
            if contact is None:
                outcomes[user_id] = "not_eligible"
                continue
            event = PrivateFriendEvent(
                contact.self_id, contact.user_id, "proactive-context", contact.nickname, "", now_ms,
            )
            idle_hours = (now_ms - contact.last_message_at) / 3_600_000
            plan = self.replies.plan_proactive(
                recent_context(self.db, event), relationship_context(self.db, event), idle_hours,
            )
            natural = next((candidate for candidate in plan.candidates if candidate.style == "natural"), None)
            if (
                plan.judgment is None or not plan.judgment.should_initiate
                or plan.judgment.confidence < self.policy.min_confidence or natural is None
            ):
                self.suggestions.write(contact, plan, sent=False, status="not_suggested", now_ms=now_ms)
                outcomes[user_id] = "not_suggested"
                continue
            if not self.send:
                self.suggestions.write(contact, plan, sent=False, status="suggested", now_ms=now_ms)
                outcomes[user_id] = "suggested"
                continue
            assert self.api is not None
            send_at_ms = now_ms if fixed_now else int(time.time() * 1000)
            if not self.policy.within_hours(send_at_ms):
                outcomes[user_id] = "quiet_hours"
                continue
            if self.api.get_self_id() != self.self_id:
                raise RuntimeError("NapCat API account changed before proactive send")
            reservation = self._reserve_attempt(contact, plan, natural.text, send_at_ms)
            if reservation != "reserved":
                outcomes[user_id] = reservation
                continue
            try:
                sent_id = self.api.send_private_text(user_id, natural.text)
            except Exception:
                self._update_attempt(contact, send_at_ms, "send_failed")
                self.suggestions.write(contact, plan, sent=False, status="send_failed", now_ms=send_at_ms)
                outcomes[user_id] = "send_failed"
                continue
            self._update_attempt(contact, send_at_ms, "sent", sent_id)
            event = PrivateFriendEvent(self.self_id, user_id, sent_id, contact.nickname, natural.text, send_at_ms)
            try:
                self.ingestor.record_outgoing(
                    event, sent_id, natural.text, send_at_ms, capture_source="onebot11_proactive",
                )
            except Exception:
                outcome = "sent_unrecorded"
            else:
                outcome = "sent"
            self.suggestions.write(contact, plan, sent=True, status=outcome, now_ms=send_at_ms)
            outcomes[user_id] = outcome
        return outcomes

    def _eligible_contact(self, user_id: str, now_ms: int) -> ProactiveContact | None:
        cid = f"qq:onebot:conversation:{self.self_id}:{user_id}"
        conversation = self.db.conversation(cid)
        if conversation is None or conversation["platform"] != "qq" or conversation["conversation_type"] != "private":
            return None
        latest = self.db.conn.execute(
            "SELECT id,message_time,direction,text FROM messages WHERE conversation_id=? "
            "ORDER BY message_time DESC,rowid DESC LIMIT 1", (cid,),
        ).fetchone()
        if latest is None or not 0 <= now_ms - int(latest["message_time"]):
            return None
        if now_ms - int(latest["message_time"]) < self.policy.idle_hours * 3_600_000:
            return None
        # A last unanswered question is a pending request, not a new opening.
        if latest["direction"] == "outgoing" and (latest["text"] or "").rstrip().endswith(("?", "？")):
            return None
        counts = self.db.conn.execute(
            "SELECT SUM(direction='incoming'),SUM(direction='outgoing') FROM messages WHERE conversation_id=?",
            (cid,),
        ).fetchone()
        if not counts or not counts[0] or not counts[1]:
            return None
        last_attempt = self.db.conn.execute(
            "SELECT attempted_at FROM qq_proactive_attempts WHERE account_id=? AND user_id=? "
            "ORDER BY attempted_at DESC LIMIT 1", (f"qq:onebot:{self.self_id}", user_id),
        ).fetchone()
        if last_attempt is not None:
            last_incoming = self.db.conn.execute(
                "SELECT MAX(message_time) FROM messages WHERE conversation_id=? AND direction='incoming'", (cid,),
            ).fetchone()[0]
            if last_incoming is None or int(last_incoming) <= int(last_attempt[0]):
                return None
        nickname = conversation["title"] or user_id
        return ProactiveContact(
            self.self_id, user_id, nickname, cid, int(latest["message_time"]), latest["id"],
        )

    def _reserve_attempt(self, contact: ProactiveContact, plan: ProactivePlan, text: str, now_ms: int) -> str:
        local_date = self.policy.local_datetime(now_ms).date().isoformat()
        topic = plan.judgment.topic if plan.judgment else None
        try:
            self.db.conn.execute("BEGIN IMMEDIATE")
            fresh = self._eligible_contact(contact.user_id, now_ms)
            if fresh is None or fresh.last_message_id != contact.last_message_id:
                self.db.conn.rollback()
                return "conversation_changed"
            self.db.conn.execute(
                "INSERT INTO qq_proactive_attempts "
                "(id,account_id,user_id,conversation_id,local_date,attempted_at,status,topic,text) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()), f"qq:onebot:{self.self_id}", contact.user_id,
                    contact.conversation_id, local_date, now_ms, "attempted", topic, text,
                ),
            )
            self.db.conn.commit()
            return "reserved"
        except sqlite3.IntegrityError:
            self.db.conn.rollback()
            return "already_attempted_today"
        except Exception:
            self.db.conn.rollback()
            raise

    def _update_attempt(self, contact: ProactiveContact, now_ms: int, status: str, sent_id: str | None = None) -> None:
        local_date = self.policy.local_datetime(now_ms).date().isoformat()
        self.db.conn.execute(
            "UPDATE qq_proactive_attempts SET status=?,onebot_message_id=? "
            "WHERE account_id=? AND user_id=? AND local_date=?",
            (status, sent_id, f"qq:onebot:{self.self_id}", contact.user_id, local_date),
        )
        self.db.conn.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-shot proactive QQ friend check-in")
    parser.add_argument("--db", default="chatweight.db")
    parser.add_argument("--schema", default=str(_default_schema()))
    parser.add_argument("--suggestions", default="qq_proactive_suggestions.json")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--self-id", default=os.getenv("CHATWEIGHT_QQ_SELF_ID", ""))
    parser.add_argument("--allow-user-id", action="append", default=[])
    parser.add_argument("--idle-hours", type=float, default=12.0)
    parser.add_argument("--local-hour-start", type=int, default=10)
    parser.add_argument("--local-hour-end", type=int, default=21)
    parser.add_argument("--utc-offset-hours", type=int, default=8)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--judge-model", default=os.getenv("CHATWEIGHT_JUDGE_MODEL", ""))
    parser.add_argument("--reply-model", default=os.getenv("CHATWEIGHT_REPLY_MODEL", ""))
    parser.add_argument("--send", action="store_true", help="send the natural draft after all gates pass")
    args = parser.parse_args(argv)

    allowed = frozenset(
        args.allow_user_id or (value.strip() for value in os.getenv("CHATWEIGHT_QQ_PROACTIVE_ALLOW_IDS", "").split(",") if value.strip())
    )
    ai_base = os.getenv("CHATWEIGHT_AI_BASE_URL", "")
    ai_key = os.getenv("CHATWEIGHT_AI_KEY", "")
    api_token = os.getenv("CHATWEIGHT_ONEBOT_TOKEN", "")
    if not args.self_id or not allowed:
        parser.error("configure --self-id and at least one --allow-user-id")
    if not ai_base or not args.judge_model or not args.reply_model or (not ai_key and not is_local_model_url(ai_base)):
        parser.error("configure the Judge and Reply models with a compatible LLM endpoint")
    if args.send and not api_token:
        parser.error("--send requires CHATWEIGHT_ONEBOT_TOKEN")
    policy = ProactivePolicy(
        idle_hours=args.idle_hours, local_hour_start=args.local_hour_start,
        local_hour_end=args.local_hour_end, utc_offset_hours=args.utc_offset_hours,
        min_confidence=args.min_confidence,
    )
    try:
        policy.validate()
    except ValueError as error:
        parser.error(str(error))
    db = ChatWeightDb(args.db, args.schema)
    try:
        replies = QQReplyEngine(ai_base, ai_key, args.judge_model, args.reply_model)
        api = OneBotApiClient(args.api_base_url, api_token) if args.send else None
        runner = QQProactiveRunner(
            db, replies, ProactiveSuggestionStore(Path(args.suggestions)),
            self_id=args.self_id, allowed_user_ids=allowed, policy=policy,
            api=api, send=args.send,
        )
        outcomes = runner.run_once()
        for user_id, outcome in outcomes.items():
            print(f"[QQ proactive] {user_id}: {outcome}")
        return 1 if any(outcome in {"send_failed", "sent_unrecorded"} for outcome in outcomes.values()) else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
