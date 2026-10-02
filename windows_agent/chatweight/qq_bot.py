"""ChatWeight personal QQ friend assistant via a local OneBot 11 gateway.

Incoming events are acknowledged quickly and processed on one worker thread.
Only text private-friend messages are accepted. Auto-send is an explicit,
allowlisted mode and still requires an affirmative AI Judge decision.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .db import ChatWeightDb
from .models import MessageDirection
from .qq_onebot import (
    OneBotApiClient, PrivateFriendEvent, QQOneBotIngestor, conversation_id,
    person_id, verify_onebot_signature,
)
from .qq_reply import QQReplyEngine, ReplyPlan, is_local_model_url


def _default_schema() -> Path:
    return Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def relationship_context(db: ChatWeightDb, event: PrivateFriendEvent) -> dict[str, object]:
    pid = person_id(event)
    profile = db.get_relationship_profile(pid, event.time_ms)
    scores: dict[str, float] = {}
    for side in ("self", "other"):
        row = db.conn.execute(
            "SELECT overall_score FROM daily_weight_snapshots WHERE person_id=? AND actor_side=? "
            "ORDER BY local_date DESC LIMIT 1", (pid, side),
        ).fetchone()
        scores[side] = float(row[0]) if row else 0.0
    return {
        "relationship_type": profile.relationship_type.value,
        "expression_stage": profile.expression_stage.value,
        "self_engagement": scores["self"],
        "other_engagement": scores["other"],
    }


def recent_context(db: ChatWeightDb, event: PrivateFriendEvent, limit: int = 12) -> list[dict[str, str]]:
    rows = db.conn.execute(
        "SELECT direction,text FROM messages WHERE conversation_id=? AND message_type='text' "
        "AND text IS NOT NULL ORDER BY rowid DESC LIMIT ?",
        (conversation_id(event), limit),
    ).fetchall()
    return [
        {"role": "assistant" if row["direction"] == "outgoing" else "user", "content": row["text"]}
        for row in reversed(rows)
    ]


class SuggestionStore:
    """Atomic local snapshot of the latest three candidates per friend."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, event: PrivateFriendEvent, plan: ReplyPlan, *, sent: bool) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, ValueError):
            existing = {}
        existing[event.user_id] = {
            "user_id": event.user_id,
            "nickname": event.nickname,
            "incoming_message_id": event.message_id,
            "updated_at": event.time_ms,
            "intent": asdict(plan.judgment) if plan.judgment else None,
            "candidates": [asdict(candidate) for candidate in plan.candidates],
            "reason": plan.reason,
            "auto_sent": sent,
        }
        pending = self.path.with_name(self.path.name + ".tmp")
        pending.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(pending, self.path)


class QQBotProcessor:
    def __init__(
        self, db: ChatWeightDb, replies: QQReplyEngine, suggestions: SuggestionStore,
        api: OneBotApiClient | None = None, *, auto_send: bool = False,
        allowed_user_ids: frozenset[str] = frozenset(), min_confidence: float = 0.7,
        max_auto_send_age_ms: int = 120_000, min_reply_gap_ms: int = 20_000,
        expected_self_id: str | None = None,
    ) -> None:
        self.db = db
        self.ingestor = QQOneBotIngestor(db)
        self.replies = replies
        self.suggestions = suggestions
        self.api = api
        self.auto_send = auto_send
        self.allowed_user_ids = allowed_user_ids
        self.min_confidence = min_confidence
        self.max_auto_send_age_ms = max_auto_send_age_ms
        self.min_reply_gap_ms = min_reply_gap_ms
        self.expected_self_id = expected_self_id

    def process(self, payload: Any) -> str:
        event = PrivateFriendEvent.parse(payload)
        if event is None:
            return "ignored"
        if self.expected_self_id and event.self_id != self.expected_self_id:
            return "foreign_account"
        if not self.ingestor.ingest(event):
            return "duplicate"
        if event.direction == MessageDirection.OUTGOING:
            return "recorded_outgoing"
        plan = self.replies.plan(recent_context(self.db, event), relationship_context(self.db, event))
        sent = False
        send_failed = False
        record_failed = False
        if self.should_auto_send(event, plan):
            candidate = next(candidate for candidate in plan.candidates if candidate.style == "natural")
            assert self.api is not None
            try:
                if self.expected_self_id and self.api.get_self_id() != self.expected_self_id:
                    raise RuntimeError("NapCat logged-in QQ account changed")
                sent_id = self.api.send_private_text(event.user_id, candidate.text)
            except Exception:
                # The incoming event is already persisted. Keep the drafts so a
                # gateway failure does not silently lose them. Never retry a
                # send automatically: its outcome may be ambiguous.
                send_failed = True
            else:
                sent = True
                try:
                    self.ingestor.record_outgoing(event, sent_id, candidate.text)
                except Exception:
                    # The message has left the gateway. Never try sending it a
                    # second time just because local accounting failed.
                    record_failed = True
        self.suggestions.write(event, plan, sent=sent)
        if record_failed:
            return "sent_unrecorded"
        if sent:
            return "sent"
        return "send_failed" if send_failed else "analyzed"

    def should_auto_send(self, event: PrivateFriendEvent, plan: ReplyPlan) -> bool:
        eligible = bool(
            self.auto_send and self.api is not None and event.user_id in self.allowed_user_ids
            and 0 <= int(time.time() * 1000) - event.time_ms <= self.max_auto_send_age_ms
            and plan.judgment is not None and plan.judgment.should_reply
            and plan.judgment.confidence >= self.min_confidence
            and any(candidate.style == "natural" and candidate.text.strip() for candidate in plan.candidates)
        )
        if not eligible:
            return False
        last_outgoing = self.db.conn.execute(
            "SELECT message_time FROM messages WHERE conversation_id=? AND direction='outgoing' "
            "ORDER BY message_time DESC LIMIT 1", (conversation_id(event),),
        ).fetchone()
        return last_outgoing is None or event.time_ms - int(last_outgoing[0]) >= self.min_reply_gap_ms


def make_handler(events: queue.Queue[Any], event_secret: str):
    class OneBotHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            body = json.dumps({"ok": True, "queued": events.qsize()}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/onebot/event":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400)
                return
            if length <= 0 or length > 256_000:
                self.send_error(413)
                return
            body = self.rfile.read(length)
            if not verify_onebot_signature(body, self.headers.get("X-Signature"), event_secret):
                self.send_error(401)
                return
            try:
                payload = json.loads(body)
            except ValueError:
                self.send_error(400)
                return
            try:
                events.put_nowait(payload)
            except queue.Full:
                self.send_error(503)
                return
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            # HTTP path/status only; never log QQ text or credentials.
            if self.path == "/health":
                return
            super().log_message(format, *args)

    return OneBotHandler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChatWeight personal QQ friend assistant (OneBot 11)")
    parser.add_argument("--db", default="chatweight.db")
    parser.add_argument("--schema", default=str(_default_schema()))
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8765)
    parser.add_argument("--suggestions", default="qq_suggestions.json")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--self-id", default=os.getenv("CHATWEIGHT_QQ_SELF_ID", ""))
    parser.add_argument("--check-account", action="store_true", help="show and verify the QQ account logged into NapCat")
    parser.add_argument("--auto-send", action="store_true")
    parser.add_argument("--allow-user-id", action="append", default=[])
    parser.add_argument("--judge-model", default=os.getenv("CHATWEIGHT_JUDGE_MODEL", ""))
    parser.add_argument("--reply-model", default=os.getenv("CHATWEIGHT_REPLY_MODEL", ""))
    args = parser.parse_args(argv)

    secret = os.getenv("CHATWEIGHT_ONEBOT_SECRET", "")
    api_token = os.getenv("CHATWEIGHT_ONEBOT_TOKEN", "")
    ai_key = os.getenv("CHATWEIGHT_AI_KEY", "")
    ai_base = os.getenv("CHATWEIGHT_AI_BASE_URL", "")
    if args.self_id and not args.self_id.isdigit():
        parser.error("--self-id must be a numeric QQ ID")
    if args.check_account:
        if not api_token:
            parser.error("--check-account requires CHATWEIGHT_ONEBOT_TOKEN")
        try:
            gateway_self_id = OneBotApiClient(args.api_base_url, api_token).get_self_id()
        except Exception:
            parser.error("cannot read the logged-in NapCat QQ account")
        if args.self_id and args.self_id != gateway_self_id:
            parser.error("configured QQ self ID differs from the account logged into NapCat")
        print(f"[QQ] logged-in account: {gateway_self_id}")
        return 0
    if not secret:
        parser.error("set CHATWEIGHT_ONEBOT_SECRET to the gateway's HTTP event secret")
    if args.listen_host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("event listener must bind to loopback")
    allowed_ids = frozenset(args.allow_user_id)
    if args.auto_send and not args.self_id:
        parser.error("--auto-send requires --self-id or CHATWEIGHT_QQ_SELF_ID")
    if args.auto_send and (not allowed_ids or not api_token or not ai_base or (not ai_key and not is_local_model_url(ai_base))):
        parser.error("--auto-send requires an allowlisted QQ ID, OneBot API token, and configured LLM")
    if any(not value.isdigit() for value in allowed_ids):
        parser.error("--allow-user-id must be a numeric QQ ID")
    if (ai_key or ai_base) and (not ai_base or not args.judge_model or not args.reply_model):
        parser.error("LLM configuration requires CHATWEIGHT_AI_BASE_URL, --judge-model, and --reply-model")
    replies = QQReplyEngine(ai_base, ai_key, args.judge_model, args.reply_model)
    api = OneBotApiClient(args.api_base_url, api_token) if args.auto_send else None
    expected_self_id = args.self_id or None
    if api is not None:
        try:
            gateway_self_id = api.get_self_id()
        except Exception:
            parser.error("cannot verify the logged-in NapCat QQ account")
        if expected_self_id and expected_self_id != gateway_self_id:
            parser.error("configured QQ self ID differs from the account logged into NapCat")
        expected_self_id = gateway_self_id
    events: queue.Queue[Any] = queue.Queue(maxsize=512)
    suggestions = SuggestionStore(Path(args.suggestions))
    ready = threading.Event()

    def worker() -> None:
        db = ChatWeightDb(args.db, args.schema)
        processor = QQBotProcessor(db, replies, suggestions, api,
                                   auto_send=args.auto_send, allowed_user_ids=allowed_ids,
                                   expected_self_id=expected_self_id)
        ready.set()
        try:
            while True:
                payload = events.get()
                if payload is None:
                    return
                try:
                    outcome = processor.process(payload)
                    if outcome != "ignored":
                        print(f"[QQ] {outcome}; total={db.message_count()}", flush=True)
                except Exception as error:
                    print(f"[QQ] processing failed: {error.__class__.__name__}", flush=True)
                finally:
                    events.task_done()
        finally:
            db.close()

    thread = threading.Thread(target=worker, name="chatweight-qq-bot", daemon=True)
    thread.start()
    ready.wait(timeout=10)
    if not ready.is_set():
        raise RuntimeError("QQ worker did not start")
    server = HTTPServer((args.listen_host, args.listen_port), make_handler(events, secret))
    print(f"[QQ] OneBot event URL: http://{args.listen_host}:{args.listen_port}/onebot/event")
    print(f"[QQ] DB: {args.db}; suggestions: {args.suggestions}; auto-send: {args.auto_send}")
    print(f"[QQ] account filter: {'****' + expected_self_id[-4:] if expected_self_id else 'not configured'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        events.put(None)
        thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
