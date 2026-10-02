from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from chatweight.qq_reply import QQReplyEngine


MESSAGES = [
    {"role": "assistant", "content": "今天忙完了吗？"},
    {"role": "user", "content": "刚忙完，今天有点累。"},
]
CONTEXT = {"relationship_type": "friend", "expression_stage": "familiarity"}
JUDGMENT = {
    "intent": "分享疲惫",
    "should_reply": True,
    "confidence": 0.91,
    "reason": "对方说明了近况",
}
REPLIES = {
    "candidates": [
        {"style": "light", "text": "终于收工啦，先歇会儿～"},
        {"style": "natural", "text": "辛苦了，先休息一下吧。"},
        {"style": "caring", "text": "今天辛苦了，吃点东西再好好休息。"},
    ]
}
PROACTIVE_JUDGMENT = {
    "topic": "上次聊到的电影",
    "should_initiate": True,
    "confidence": 0.92,
    "reason": "有自然的后续话题",
}


def completion(content: object) -> io.BytesIO:
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    return io.BytesIO(
        json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode("utf-8")
    )


class QQReplyEngineTests(unittest.TestCase):
    def make_engine(self, api_key: str = "test-key") -> QQReplyEngine:
        return QQReplyEngine("https://model.example/v1/", api_key, "judge-model", "reply-model", 7)

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_no_api_key_makes_no_request(self, urlopen):
        plan = self.make_engine("  ").plan(MESSAGES, CONTEXT)
        self.assertIsNone(plan.judgment)
        self.assertEqual(plan.candidates, ())
        self.assertEqual(plan.reason, "missing_api_key")
        urlopen.assert_not_called()

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_local_model_can_run_without_api_key(self, urlopen):
        urlopen.side_effect = [completion(JUDGMENT), completion(REPLIES)]
        engine = QQReplyEngine("http://127.0.0.1:11434/v1", "", "local-judge", "local-reply")
        plan = engine.plan(MESSAGES, CONTEXT)
        self.assertEqual(plan.reason, "ready")
        self.assertEqual(len(plan.candidates), 3)
        self.assertFalse(urlopen.call_args_list[0].args[0].has_header("Authorization"))

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_remote_plain_http_model_is_rejected(self, urlopen):
        engine = QQReplyEngine("http://model.example/v1", "test-key", "judge", "reply")
        self.assertEqual(engine.plan(MESSAGES, CONTEXT).reason, "invalid_config")
        urlopen.assert_not_called()

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_latest_message_must_be_from_friend(self, urlopen):
        plan = self.make_engine().plan(MESSAGES + [{"role": "assistant", "content": "收到"}], CONTEXT)
        self.assertEqual(plan.reason, "no_target_message")
        self.assertEqual(plan.candidates, ())
        urlopen.assert_not_called()

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_judge_then_reply_with_original_judgment(self, urlopen):
        urlopen.side_effect = [completion(JUDGMENT), completion(REPLIES)]

        plan = self.make_engine().plan(MESSAGES, CONTEXT)

        self.assertEqual(plan.reason, "ready")
        self.assertEqual(plan.judgment.intent, JUDGMENT["intent"])
        self.assertEqual(plan.judgment.reason, JUDGMENT["reason"])
        self.assertEqual(plan.judgment.confidence, JUDGMENT["confidence"])
        self.assertEqual(tuple(candidate.style for candidate in plan.candidates), ("natural", "caring", "light"))
        self.assertEqual(len(plan.candidates), 3)
        self.assertEqual(urlopen.call_count, 2)

        judge_request = urlopen.call_args_list[0].args[0]
        reply_request = urlopen.call_args_list[1].args[0]
        self.assertEqual(judge_request.full_url, "https://model.example/v1/chat/completions")
        self.assertEqual(urlopen.call_args_list[0].kwargs["timeout"], 7)
        judge_body = json.loads(judge_request.data)
        reply_body = json.loads(reply_request.data)
        self.assertEqual(judge_body["model"], "judge-model")
        self.assertEqual(reply_body["model"], "reply-model")
        self.assertEqual(json.loads(reply_body["messages"][1]["content"])["intent_judgment"], JUDGMENT)

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_no_reply_judgment_skips_drafting(self, urlopen):
        decision = {**JUDGMENT, "should_reply": False}
        urlopen.return_value = completion(decision)

        plan = self.make_engine().plan(MESSAGES, CONTEXT)

        self.assertEqual(plan.reason, "judged_no_reply")
        self.assertFalse(plan.judgment.should_reply)
        self.assertEqual(plan.candidates, ())
        urlopen.assert_called_once()

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_accepts_fenced_json(self, urlopen):
        urlopen.side_effect = [
            completion("```json\n" + json.dumps(JUDGMENT, ensure_ascii=False) + "\n```"),
            completion("```json\n" + json.dumps(REPLIES, ensure_ascii=False) + "\n```"),
        ]
        plan = self.make_engine().plan(MESSAGES, CONTEXT)
        self.assertEqual(plan.reason, "ready")
        self.assertEqual(len(plan.candidates), 3)

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_rejects_invalid_judgment_without_drafting(self, urlopen):
        urlopen.return_value = completion({**JUDGMENT, "confidence": 2.0})
        plan = self.make_engine().plan(MESSAGES, CONTEXT)
        self.assertEqual(plan.reason, "invalid_judgment_response")
        self.assertIsNone(plan.judgment)
        self.assertEqual(plan.candidates, ())
        urlopen.assert_called_once()

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_rejects_incomplete_drafts_but_keeps_judgment(self, urlopen):
        urlopen.side_effect = [completion(JUDGMENT), completion({"candidates": REPLIES["candidates"][:2]})]
        plan = self.make_engine().plan(MESSAGES, CONTEXT)
        self.assertEqual(plan.reason, "invalid_reply_response")
        self.assertEqual(plan.judgment.intent, JUDGMENT["intent"])
        self.assertEqual(plan.candidates, ())

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_request_error_fails_closed_without_exposing_exception(self, urlopen):
        urlopen.side_effect = OSError("secret-bearing upstream error")
        plan = self.make_engine().plan(MESSAGES, CONTEXT)
        self.assertEqual(plan.reason, "judge_request_failed")
        self.assertNotIn("secret", plan.reason)
        self.assertEqual(plan.candidates, ())

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_proactive_judge_then_three_openers(self, urlopen):
        urlopen.side_effect = [completion(PROACTIVE_JUDGMENT), completion(REPLIES)]
        plan = self.make_engine().plan_proactive(MESSAGES, CONTEXT, 12.0)
        self.assertEqual(plan.reason, "ready")
        self.assertEqual(plan.judgment.topic, PROACTIVE_JUDGMENT["topic"])
        self.assertEqual(len(plan.candidates), 3)
        reply_body = json.loads(urlopen.call_args_list[1].args[0].data)
        self.assertEqual(json.loads(reply_body["messages"][1]["content"])["initiation_judgment"], PROACTIVE_JUDGMENT)

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_proactive_negative_judge_does_not_draft(self, urlopen):
        urlopen.return_value = completion({**PROACTIVE_JUDGMENT, "should_initiate": False})
        plan = self.make_engine().plan_proactive(MESSAGES, CONTEXT, 12.0)
        self.assertEqual(plan.reason, "judged_no_initiation")
        self.assertEqual(plan.candidates, ())
        urlopen.assert_called_once()

    @patch("chatweight.qq_reply.urllib.request.urlopen")
    def test_proactive_invalid_judge_fails_closed(self, urlopen):
        urlopen.return_value = completion({**PROACTIVE_JUDGMENT, "confidence": 1.5})
        plan = self.make_engine().plan_proactive(MESSAGES, CONTEXT, 12.0)
        self.assertEqual(plan.reason, "invalid_judgment_response")
        self.assertIsNone(plan.judgment)
        self.assertEqual(plan.candidates, ())


if __name__ == "__main__":
    unittest.main()
