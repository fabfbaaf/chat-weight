"""Checks for the 12-hour, allowlisted proactive QQ sender."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from chatweight.db import ChatWeightDb
from chatweight.qq_onebot import PrivateFriendEvent, QQOneBotIngestor
from chatweight.qq_proactive import ProactivePolicy, ProactiveSuggestionStore, QQProactiveRunner
from chatweight.qq_reply import ProactiveJudgment, ProactivePlan, ReplyCandidate


ROOT = Path(__file__).resolve().parents[2]
NOW_MS = int(datetime(2026, 9, 26, 4, 0, tzinfo=timezone.utc).timestamp() * 1000)
SELF_ID = "12345678"
FRIEND_ID = "87654321"


def ready_plan() -> ProactivePlan:
    return ProactivePlan(
        ProactiveJudgment("上次聊到的电影", True, 0.91, "有自然的话题"),
        (
            ReplyCandidate("natural", "上次说的电影你后来有看吗？"),
            ReplyCandidate("caring", "最近还好吗？"),
            ReplyCandidate("light", "突然想起上次聊的电影～"),
        ),
        "ready",
    )


class ProactiveRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = ChatWeightDb(Path(self.temp.name) / "chatweight.db", ROOT / "sql" / "schema.sql")
        self.ingestor = QQOneBotIngestor(self.db)
        self.replies = Mock()
        self.replies.plan_proactive.return_value = ready_plan()
        self.api = Mock()
        self.api.get_self_id.return_value = SELF_ID
        self.api.send_private_text.return_value = "901"
        self.suggestions_path = Path(self.temp.name) / "proactive.json"

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def seed_history(self, last_at_ms: int = NOW_MS - 13 * 3_600_000, last_text: str = "周末聊电影") -> None:
        first = PrivateFriendEvent(
            SELF_ID, FRIEND_ID, "100", "小雨", "最近有什么好看的电影", last_at_ms - 60_000,
        )
        self.assertTrue(self.ingestor.ingest(first))
        self.assertTrue(self.ingestor.record_outgoing(first, "101", last_text, last_at_ms))

    def runner(self, *, send: bool = False, allowed: frozenset[str] | None = None) -> QQProactiveRunner:
        return QQProactiveRunner(
            self.db, self.replies, ProactiveSuggestionStore(self.suggestions_path),
            self_id=SELF_ID, allowed_user_ids=allowed or frozenset({FRIEND_ID}),
            policy=ProactivePolicy(), api=self.api if send else None, send=send,
        )

    def test_preview_after_12_hours_writes_three_candidates_without_sending(self) -> None:
        self.seed_history()
        self.assertEqual(self.runner().run_once(NOW_MS), {FRIEND_ID: "suggested"})
        data = json.loads(self.suggestions_path.read_text(encoding="utf-8"))[FRIEND_ID]
        self.assertEqual([item["style"] for item in data["candidates"]], ["natural", "caring", "light"])
        self.assertFalse(data["auto_sent"])
        self.assertEqual(self.db.message_count(), 2)
        self.api.send_private_text.assert_not_called()

    def test_idle_threshold_and_local_daytime(self) -> None:
        self.seed_history(NOW_MS - 12 * 3_600_000 + 1)
        self.assertEqual(self.runner().run_once(NOW_MS), {FRIEND_ID: "not_eligible"})
        self.assertEqual(self.runner().run_once(NOW_MS - 3 * 3_600_000), {FRIEND_ID: "quiet_hours"})
        self.replies.plan_proactive.assert_not_called()

    def test_send_reserves_once_and_records_outgoing(self) -> None:
        self.seed_history()
        runner = self.runner(send=True)
        self.assertEqual(runner.run_once(NOW_MS), {FRIEND_ID: "sent"})
        self.api.send_private_text.assert_called_once_with(FRIEND_ID, "上次说的电影你后来有看吗？")
        row = self.db.conn.execute("SELECT * FROM qq_proactive_attempts").fetchone()
        self.assertEqual((row["status"], row["onebot_message_id"], row["local_date"]), ("sent", "901", "2026-09-26"))
        outgoing = self.db.conn.execute(
            "SELECT text,capture_source FROM messages WHERE direction='outgoing' ORDER BY message_time DESC LIMIT 1"
        ).fetchone()
        self.assertEqual((outgoing["text"], outgoing["capture_source"]), ("上次说的电影你后来有看吗？", "onebot11_proactive"))
        self.assertEqual(runner.run_once(NOW_MS + 24 * 3_600_000), {FRIEND_ID: "not_eligible"})
        self.api.send_private_text.assert_called_once()

    def test_requires_new_incoming_after_previous_attempt(self) -> None:
        self.seed_history()
        runner = self.runner(send=True)
        self.assertEqual(runner.run_once(NOW_MS), {FRIEND_ID: "sent"})
        next_day = NOW_MS + 24 * 3_600_000
        self.assertEqual(runner.run_once(next_day), {FRIEND_ID: "not_eligible"})
        reply = PrivateFriendEvent(SELF_ID, FRIEND_ID, "902", "小雨", "看了，还不错", next_day - 13 * 3_600_000)
        self.assertTrue(self.ingestor.ingest(reply))
        self.assertEqual(runner.run_once(next_day), {FRIEND_ID: "sent"})
        self.assertEqual(self.api.send_private_text.call_count, 2)

    def test_negative_judge_low_confidence_and_unanswered_question_do_not_send(self) -> None:
        self.seed_history(last_text="周末有空吗？")
        self.assertEqual(self.runner(send=True).run_once(NOW_MS), {FRIEND_ID: "not_eligible"})
        self.replies.plan_proactive.assert_not_called()
        # A fresh conversation without a pending question is still gated by Judge.
        later = PrivateFriendEvent(SELF_ID, FRIEND_ID, "102", "小雨", "先忙了", NOW_MS - 13 * 3_600_000)
        self.assertTrue(self.ingestor.ingest(later))
        self.replies.plan_proactive.return_value = replace(ready_plan(), judgment=replace(ready_plan().judgment, should_initiate=False))
        self.assertEqual(self.runner(send=True).run_once(NOW_MS), {FRIEND_ID: "not_suggested"})
        self.replies.plan_proactive.return_value = replace(ready_plan(), judgment=replace(ready_plan().judgment, confidence=0.84))
        self.assertEqual(self.runner(send=True).run_once(NOW_MS), {FRIEND_ID: "not_suggested"})
        self.api.send_private_text.assert_not_called()

    def test_account_mismatch_blocks_send(self) -> None:
        self.seed_history()
        self.api.get_self_id.return_value = "99999999"
        with self.assertRaisesRegex(RuntimeError, "account"):
            self.runner(send=True).run_once(NOW_MS)
        self.api.send_private_text.assert_not_called()
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM qq_proactive_attempts").fetchone()[0], 0)

    def test_new_message_during_model_call_cancels_proactive_send(self) -> None:
        self.seed_history()

        def plan_and_receive(*_args: object) -> ProactivePlan:
            incoming = PrivateFriendEvent(SELF_ID, FRIEND_ID, "103", "小雨", "现在有空", NOW_MS - 1000)
            self.assertTrue(self.ingestor.ingest(incoming))
            return ready_plan()

        self.replies.plan_proactive.side_effect = plan_and_receive
        self.assertEqual(self.runner(send=True).run_once(NOW_MS), {FRIEND_ID: "conversation_changed"})
        self.api.send_private_text.assert_not_called()

    def test_failed_send_is_reserved_and_never_retried_without_reply(self) -> None:
        self.seed_history()
        self.api.send_private_text.side_effect = OSError("uncertain response")
        runner = self.runner(send=True)
        self.assertEqual(runner.run_once(NOW_MS), {FRIEND_ID: "send_failed"})
        self.assertEqual(self.db.conn.execute("SELECT status FROM qq_proactive_attempts").fetchone()[0], "send_failed")
        self.assertEqual(runner.run_once(NOW_MS + 24 * 3_600_000), {FRIEND_ID: "not_eligible"})
        self.api.send_private_text.assert_called_once()


if __name__ == "__main__":
    unittest.main()
