"""Contract tests for the local OneBot 11 personal QQ bridge."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import queue
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from chatweight.db import ChatWeightDb
from chatweight.qq_bot import QQBotProcessor, SuggestionStore, make_handler
from chatweight.qq_onebot import (
    OneBotApiClient,
    PrivateFriendEvent,
    QQOneBotIngestor,
    conversation_id,
    person_id,
    verify_onebot_signature,
)
from chatweight.qq_reply import IntentJudgment, ReplyCandidate, ReplyPlan


ROOT = Path(__file__).resolve().parents[2]
AT_SECONDS = int(time.time())


def friend_payload(message_id: int = 100, text: str = "今天有点累") -> dict[str, object]:
    return {
        "post_type": "message",
        "message_type": "private",
        "sub_type": "friend",
        "self_id": 12345678,
        "user_id": 87654321,
        "message_id": message_id,
        "time": AT_SECONDS,
        "sender": {"nickname": "小雨"},
        "message": [{"type": "text", "data": {"text": text}}],
    }


def reply_plan(*, should_reply: bool = True, confidence: float = 0.92) -> ReplyPlan:
    return ReplyPlan(
        IntentJudgment("分享近况", should_reply, confidence, "对方说今天累了"),
        (
            ReplyCandidate("natural", "辛苦了，先休息会儿吧。"),
            ReplyCandidate("caring", "今天辛苦了，记得吃点东西。"),
            ReplyCandidate("light", "终于收工啦，先歇会儿～"),
        ),
        "ready",
    )


class OneBotEventTests(unittest.TestCase):
    def test_accepts_private_friend_text_with_stable_ids(self) -> None:
        event = PrivateFriendEvent.parse(friend_payload())
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.text, "今天有点累")
        self.assertEqual(event.nickname, "小雨")
        self.assertEqual(event.time_ms, AT_SECONDS * 1000)
        self.assertEqual(conversation_id(event), "qq:onebot:conversation:12345678:87654321")
        self.assertEqual(person_id(event), "qq:onebot:person:12345678:87654321")

    def test_filters_group_temporary_self_and_non_text_messages(self) -> None:
        base = friend_payload()
        variants = (
            {**base, "message_type": "group"},
            {**base, "sub_type": "group"},
            {key: value for key, value in base.items() if key != "sub_type"},
            {**base, "post_type": "notice"},
            {**base, "user_id": base["self_id"]},
            {**base, "message": [{"type": "image", "data": {"file": "x.png"}}]},
            {**base, "message": "hello[CQ:image,file=x.png]"},
            {**base, "message": "   "},
            {**base, "message": "x" * 4001},
        )
        for payload in variants:
            with self.subTest(payload=payload.get("message_type"), subtype=payload.get("sub_type")):
                self.assertIsNone(PrivateFriendEvent.parse(payload))

    def test_raw_message_fallback_only_when_message_absent(self) -> None:
        base = friend_payload()
        event = PrivateFriendEvent.parse({**base, "message": None, "raw_message": "  你好  "})
        self.assertEqual(event.text, "你好")
        self.assertIsNone(PrivateFriendEvent.parse({**base, "message": [{"type": "image", "data": {}}], "raw_message": "你好"}))

    def test_self_message_uses_target_friend_and_outgoing_direction(self) -> None:
        payload = {**friend_payload(), "user_id": 12345678, "target_id": 87654321,
                   "sender": {"nickname": "我的昵称"}, "message": "我手动回复了"}
        event = PrivateFriendEvent.parse(payload)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.user_id, "87654321")
        self.assertEqual(event.direction.value, "outgoing")
        self.assertEqual(event.nickname, "87654321")

    def test_signature_requires_valid_hmac_over_exact_body(self) -> None:
        body = json.dumps(friend_payload(), ensure_ascii=False).encode("utf-8")
        secret = "event-secret"
        signature = "sha1=" + hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
        self.assertTrue(verify_onebot_signature(body, signature, secret))
        self.assertFalse(verify_onebot_signature(body + b" ", signature, secret))
        self.assertFalse(verify_onebot_signature(body, signature, "wrong-secret"))
        self.assertFalse(verify_onebot_signature(body, None, secret))
        self.assertFalse(verify_onebot_signature(body, signature, ""))


class OneBotSqliteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = ChatWeightDb(Path(self.temp.name) / "chatweight.db", ROOT / "sql" / "schema.sql")
        self.ingestor = QQOneBotIngestor(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_incoming_message_creates_private_conversation_and_analysis(self) -> None:
        event = PrivateFriendEvent.parse(friend_payload())
        assert event is not None
        self.assertTrue(self.ingestor.ingest(event))
        self.assertEqual(self.db.message_count(), 1)
        row = self.db.recent_messages(1)[0]
        self.assertEqual(row["platform"], "qq")
        self.assertEqual(row["direction"], "incoming")
        self.assertEqual(row["person_id"], person_id(event))
        self.assertEqual(row["conversation_id"], conversation_id(event))
        self.assertEqual(row["account_id"], "qq:onebot:12345678")
        self.assertEqual(row["capture_source"], "onebot11_private")
        convo = self.db.conversation(conversation_id(event))
        self.assertEqual(convo["conversation_type"], "private")
        self.assertEqual(convo["primary_person_id"], person_id(event))
        self.assertGreater(
            self.db.conn.execute("SELECT COUNT(*) FROM weight_events WHERE person_id=?", (person_id(event),)).fetchone()[0],
            0,
        )
        self.assertGreater(
            self.db.conn.execute("SELECT COUNT(*) FROM daily_weight_snapshots WHERE person_id=?", (person_id(event),)).fetchone()[0],
            0,
        )

    def test_replayed_event_is_deduplicated_across_ingestor_restart(self) -> None:
        first = PrivateFriendEvent.parse(friend_payload())
        assert first is not None
        self.assertTrue(self.ingestor.ingest(first))
        weight_count = self.db.conn.execute("SELECT COUNT(*) FROM weight_events").fetchone()[0]
        restarted = QQOneBotIngestor(self.db)
        self.assertFalse(restarted.ingest(first))
        self.assertEqual(self.db.message_count(), 1)
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM weight_events").fetchone()[0], weight_count)

        second = replace(first, message_id="101", text="又来一条", time_ms=first.time_ms + 60_000)
        self.assertTrue(restarted.ingest(second))
        session_rows = self.db.conn.execute(
            "SELECT message_count FROM chat_sessions WHERE conversation_id=?", (conversation_id(first),)
        ).fetchall()
        self.assertEqual([row[0] for row in session_rows], [2])
        starts = self.db.conn.execute(
            "SELECT COUNT(*) FROM weight_events WHERE person_id=? AND event_type='session_start'", (person_id(first),)
        ).fetchone()[0]
        self.assertEqual(starts, 1)

    def test_outgoing_is_stored_with_own_sender_and_deduplicated(self) -> None:
        event = PrivateFriendEvent.parse(friend_payload())
        assert event is not None
        self.assertTrue(self.ingestor.ingest(event))
        self.assertTrue(self.ingestor.record_outgoing(event, "900", "辛苦了", event.time_ms + 1000))
        self.assertFalse(self.ingestor.record_outgoing(event, "900", "辛苦了", event.time_ms + 1000))
        self.assertEqual(self.db.message_count(), 2)
        outgoing = self.db.conn.execute("SELECT * FROM messages WHERE direction='outgoing'").fetchone()
        self.assertEqual(outgoing["sender_id"], event.self_id)
        self.assertEqual(outgoing["text"], "辛苦了")


class OneBotProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = ChatWeightDb(Path(self.temp.name) / "chatweight.db", ROOT / "sql" / "schema.sql")
        self.suggestions_path = Path(self.temp.name) / "suggestions.json"
        self.suggestions = SuggestionStore(self.suggestions_path)
        self.replies = Mock()
        self.replies.plan.return_value = reply_plan()
        self.api = Mock()
        self.api.send_private_text.return_value = "901"

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_suggestions_saved_but_no_send_by_default(self) -> None:
        processor = QQBotProcessor(self.db, self.replies, self.suggestions, self.api)
        self.assertEqual(processor.process(friend_payload()), "analyzed")
        self.api.send_private_text.assert_not_called()
        data = json.loads(self.suggestions_path.read_text(encoding="utf-8"))["87654321"]
        self.assertEqual(data["intent"]["intent"], "分享近况")
        self.assertEqual([item["style"] for item in data["candidates"]], ["natural", "caring", "light"])
        self.assertFalse(data["auto_sent"])
        self.assertEqual(self.db.message_count(), 1)
        self.assertEqual(processor.process(friend_payload()), "duplicate")
        self.replies.plan.assert_called_once()

    def test_auto_send_requires_allowlist_and_records_sent_message(self) -> None:
        processor = QQBotProcessor(
            self.db, self.replies, self.suggestions, self.api,
            auto_send=True, allowed_user_ids=frozenset({"87654321"}),
        )
        self.assertEqual(processor.process(friend_payload()), "sent")
        self.api.send_private_text.assert_called_once_with("87654321", "辛苦了，先休息会儿吧。")
        self.assertEqual(self.db.message_count(), 2)
        data = json.loads(self.suggestions_path.read_text(encoding="utf-8"))["87654321"]
        self.assertTrue(data["auto_sent"])
        self.assertEqual(processor.process(friend_payload()), "duplicate")
        self.api.send_private_text.assert_called_once()

    def test_gateway_send_failure_still_preserves_suggestions(self) -> None:
        self.api.send_private_text.side_effect = OSError("gateway unavailable")
        processor = QQBotProcessor(
            self.db, self.replies, self.suggestions, self.api,
            auto_send=True, allowed_user_ids=frozenset({"87654321"}),
        )
        processor.process(friend_payload())
        data = json.loads(self.suggestions_path.read_text(encoding="utf-8"))["87654321"]
        self.assertFalse(data["auto_sent"])
        self.assertEqual(len(data["candidates"]), 3)
        self.assertEqual(self.db.message_count(), 1)

    def test_successful_send_is_not_retried_when_local_record_fails(self) -> None:
        processor = QQBotProcessor(
            self.db, self.replies, self.suggestions, self.api,
            auto_send=True, allowed_user_ids=frozenset({"87654321"}),
        )
        processor.ingestor.record_outgoing = Mock(side_effect=OSError("disk unavailable"))
        self.assertEqual(processor.process(friend_payload()), "sent_unrecorded")
        self.api.send_private_text.assert_called_once()
        self.assertTrue(json.loads(self.suggestions_path.read_text(encoding="utf-8"))["87654321"]["auto_sent"])
        self.assertEqual(processor.process(friend_payload()), "duplicate")
        self.api.send_private_text.assert_called_once()

    def test_no_auto_send_for_unlisted_contact_negative_judge_or_low_confidence(self) -> None:
        cases = (
            (frozenset(), reply_plan()),
            (frozenset({"87654321"}), reply_plan(should_reply=False)),
            (frozenset({"87654321"}), reply_plan(confidence=0.69)),
            (frozenset({"87654321"}), ReplyPlan(None, (), "missing_api_key")),
        )
        for index, (allowed, plan) in enumerate(cases):
            with self.subTest(index=index):
                self.replies.plan.return_value = plan
                processor = QQBotProcessor(
                    self.db, self.replies, self.suggestions, self.api,
                    auto_send=True, allowed_user_ids=allowed,
                )
                self.assertEqual(processor.process(friend_payload(200 + index)), "analyzed")
        self.api.send_private_text.assert_not_called()
        self.assertEqual(self.db.message_count(), 4)

    def test_delayed_event_is_analyzed_but_not_auto_sent(self) -> None:
        processor = QQBotProcessor(
            self.db, self.replies, self.suggestions, self.api,
            auto_send=True, allowed_user_ids=frozenset({"87654321"}),
        )
        stale = {**friend_payload(), "time": AT_SECONDS - 3600}
        self.assertEqual(processor.process(stale), "analyzed")
        self.api.send_private_text.assert_not_called()
        self.assertEqual(self.db.message_count(), 1)

    def test_burst_messages_do_not_trigger_two_auto_replies(self) -> None:
        processor = QQBotProcessor(
            self.db, self.replies, self.suggestions, self.api,
            auto_send=True, allowed_user_ids=frozenset({"87654321"}),
        )
        self.assertEqual(processor.process({**friend_payload(), "time": AT_SECONDS - 2}), "sent")
        self.assertEqual(processor.process(friend_payload(101, "还有一件事")), "analyzed")
        self.api.send_private_text.assert_called_once()
        self.assertEqual(self.db.message_count(), 3)

    def test_self_message_updates_analysis_without_invoking_ai_or_send(self) -> None:
        processor = QQBotProcessor(
            self.db, self.replies, self.suggestions, self.api,
            auto_send=True, allowed_user_ids=frozenset({"87654321"}),
        )
        self.assertEqual(processor.process(friend_payload()), "sent")
        self.replies.plan.reset_mock()
        self.api.send_private_text.reset_mock()
        self.assertEqual(processor.process({**friend_payload(102, "我手动回复了"),
                                            "user_id": 12345678, "target_id": 87654321}),
                         "recorded_outgoing")
        self.replies.plan.assert_not_called()
        self.api.send_private_text.assert_not_called()
        self.assertEqual(self.db.message_count(), 3)
        self.assertEqual(self.db.conversation("qq:onebot:conversation:12345678:87654321")["title"], "小雨")

    def test_account_filter_rejects_foreign_events_and_rechecks_before_send(self) -> None:
        self.api.get_self_id.return_value = "99999999"
        processor = QQBotProcessor(
            self.db, self.replies, self.suggestions, self.api,
            auto_send=True, allowed_user_ids=frozenset({"87654321"}), expected_self_id="12345678",
        )
        foreign = {**friend_payload(), "self_id": 99999999}
        self.assertEqual(processor.process(foreign), "foreign_account")
        self.assertEqual(self.db.message_count(), 0)
        self.assertEqual(processor.process(friend_payload()), "send_failed")
        self.api.send_private_text.assert_not_called()
        self.assertEqual(self.db.message_count(), 1)


class OneBotHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events: queue.Queue[object] = queue.Queue(maxsize=1)
        self.secret = "event-secret"
        self.server = HTTPServer(("127.0.0.1", 0), make_handler(self.events, self.secret))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def post(self, body: bytes, signature: str | None) -> int:
        headers = {"Content-Type": "application/json"}
        if signature is not None:
            headers["X-Signature"] = signature
        request = Request(self.base_url + "/onebot/event", data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=3) as response:
                return response.status
        except HTTPError as error:
            return error.code

    def test_signed_event_queued_once_and_unsigned_rejected(self) -> None:
        body = json.dumps(friend_payload(), ensure_ascii=False).encode("utf-8")
        signature = "sha1=" + hmac.new(self.secret.encode(), body, hashlib.sha1).hexdigest()
        self.assertEqual(self.post(body, None), 401)
        self.assertEqual(self.events.qsize(), 0)
        self.assertEqual(self.post(body, signature), 204)
        self.assertEqual(self.events.get_nowait(), friend_payload())

    def test_full_queue_returns_service_unavailable(self) -> None:
        self.events.put_nowait({"existing": True})
        body = b"{}"
        signature = "sha1=" + hmac.new(self.secret.encode(), body, hashlib.sha1).hexdigest()
        self.assertEqual(self.post(body, signature), 503)
        self.assertEqual(self.events.qsize(), 1)


class OneBotApiClientTests(unittest.TestCase):
    def test_refuses_nonlocal_api(self) -> None:
        with self.assertRaises(ValueError):
            OneBotApiClient("https://example.com", "token")

    @patch("chatweight.qq_onebot.urlopen")
    def test_sends_plain_private_text_with_token(self, mocked_urlopen: Mock) -> None:
        mocked_urlopen.return_value = io.BytesIO(b'{"status":"ok","data":{"message_id":901}}')
        api = OneBotApiClient("http://127.0.0.1:3000", "secret-token")
        self.assertEqual(api.send_private_text("87654321", "你好[CQ:at,qq=42]"), "901")
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:3000/send_private_msg")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        self.assertEqual(json.loads(request.data), {
            "user_id": 87654321,
            "message": "你好[CQ:at,qq=42]",
            "auto_escape": True,
        })

    @patch("chatweight.qq_onebot.urlopen")
    def test_reads_logged_in_qq_account_with_token(self, mocked_urlopen: Mock) -> None:
        mocked_urlopen.return_value = io.BytesIO(b'{"status":"ok","data":{"user_id":12345678}}')
        api = OneBotApiClient("http://127.0.0.1:3000", "secret-token")
        self.assertEqual(api.get_self_id(), "12345678")
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:3000/get_login_info")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")


if __name__ == "__main__":
    unittest.main()
