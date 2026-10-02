from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from chatweight.detectors import DetectionContext, RelationshipEventDetector
from chatweight.engines import RelationshipEngine, RelationshipHeatEngine, score_from_raw
from chatweight.models import (
    ActorSide,
    CandidateStatus,
    ConfirmationPolicy,
    DetectionSource,
    ExpressionStage,
    MessageDirection,
    MessageType,
    Platform,
    RelationshipEventCandidate,
    RelationshipEventType,
    RelationshipProfileState,
    RelationshipType,
    UnifiedMessage,
)


ROOT = Path(__file__).resolve().parents[2]


def msg(text: str, direction: MessageDirection, ts: int, mid="m1") -> UnifiedMessage:
    return UnifiedMessage(
        id=mid,
        platform=Platform.WECHAT,
        conversation_id="c1",
        person_id="p1",
        direction=direction,
        message_type=MessageType.TEXT,
        text=text,
        message_time=ts,
        captured_at=ts,
        fingerprint=mid,
    )


class TestCore(unittest.TestCase):
    def test_schema_loads(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
            names = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
            self.assertIn("relationship_profile", names)
            self.assertIn("weight_events", names)
            self.assertIn("messages", names)
        finally:
            conn.close()

    def test_score_saturates(self):
        self.assertAlmostEqual(score_from_raw(0), 0.0)
        self.assertGreater(score_from_raw(40), 80)
        self.assertLessEqual(score_from_raw(1000), 100.0)
        self.assertGreater(score_from_raw(1000), 99.0)

    def test_missing_phrase_detected(self):
        d = RelationshipEventDetector()
        m = msg("今天突然有点想你了", MessageDirection.OUTGOING, 1000)
        events = d.detect(DetectionContext(m, [], None, set()))
        types = {e.event_type for e in events}
        self.assertIn(RelationshipEventType.LIGHT_MISSING_EXPRESSION, types)

    def test_negative_missing_not_detected(self):
        d = RelationshipEventDetector()
        m = msg("谁想你了", MessageDirection.OUTGOING, 1000)
        events = d.detect(DetectionContext(m, [], None, set()))
        types = {e.event_type for e in events}
        self.assertNotIn(RelationshipEventType.LIGHT_MISSING_EXPRESSION, types)

    def test_direct_like_requires_review(self):
        d = RelationshipEventDetector()
        m = msg("其实我挺喜欢你的", MessageDirection.OUTGOING, 1000)
        events = d.detect(DetectionContext(m, [], None, set()))
        item = next(e for e in events if e.event_type == RelationshipEventType.DIRECT_LIKE_EXPRESSION)
        self.assertEqual(item.confirmation_policy, ConfirmationPolicy.USER_REVIEW)
        self.assertEqual(item.status, CandidateStatus.PENDING)

    def test_stage_direct_expression_hard_gate(self):
        profile = RelationshipProfileState(
            person_id="p1",
            relationship_type=RelationshipType.CRUSH,
            expression_raw=90,
            expression_stage=ExpressionStage.OBVIOUS_CARE,
            highest_expression_stage=ExpressionStage.OBVIOUS_CARE,
            heat_updated_at=1000,
            updated_at=1000,
        )
        candidate = RelationshipEventCandidate(
            id="e1", person_id="p1", conversation_id="c1", actor_side=ActorSide.SELF,
            event_type=RelationshipEventType.LIGHT_MISSING_EXPRESSION,
            source=DetectionSource.LOCAL_SEMANTIC_RULE, confidence=1,
            confirmation_policy=ConfirmationPolicy.HIGH_CONFIDENCE_ONLY,
            status=CandidateStatus.CONFIRMED, event_time=2000,
        )
        evidence = {
            "valid_sessions_30d": 10,
            "approach_event_count_14d": 10,
            "distinct_care_event_types_30d": 4,
            "has_affection_event": True,
            "has_direct_expression_event": False,
            "relationship_confirmed": False,
        }
        updated = RelationshipEngine.apply(profile, candidate, evidence)
        self.assertEqual(updated.expression_stage, ExpressionStage.LIGHT_AFFECTION)
        self.assertLess(updated.expression_stage, ExpressionStage.DIRECT_EXPRESSION)

    def test_heat_decays(self):
        raw = 10.0
        later = 14 * 86_400_000
        self.assertAlmostEqual(RelationshipHeatEngine.decay(raw, 0, later), 5.0, places=5)


if __name__ == "__main__":
    unittest.main()

class TestWeChatSqliteIngestor(unittest.TestCase):
    def setUp(self):
        from chatweight.db import ChatWeightDb
        from chatweight.wechat_live import WeChatSqliteIngestor
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "chatweight.db"
        self.db = ChatWeightDb(self.db_path, ROOT / "sql" / "schema.sql")
        self.ingestor = WeChatSqliteIngestor(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_private_chat_lines_enter_sqlite(self):
        r = self.ingestor.ingest_batch(
            "小雨",
            [("her", None, "在吗"), ("me", None, "在呀")],
            1_700_000_000_000,
        )
        self.assertEqual(r.inserted, 2)
        self.assertEqual(r.conversation_type, "private")
        rows = self.db.recent_messages(10)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["person_id"] for row in rows))
        self.assertTrue(all(row["capture_source"] == "jev_windows_wgc_rapidocr" for row in rows))

    def test_group_members_are_group_scoped(self):
        r = self.ingestor.ingest_batch(
            "周末小分队",
            [("her", "Alice", "到了"), ("her", "Bob", "马上")],
            1_700_000_001_000,
        )
        self.assertEqual(r.conversation_type, "group")
        rows = self.db.recent_messages(10)
        person_ids = {row["person_id"] for row in rows}
        self.assertEqual(len(person_ids), 2)
        convo = self.db.conversation(r.conversation_id)
        self.assertEqual(convo["conversation_type"], "group")
        self.assertIsNone(convo["primary_person_id"])

    def test_outgoing_unknown_then_private_backfills_person(self):
        r1 = self.ingestor.ingest_batch(
            "小雨",
            [("me", None, "在吗")],
            1_700_000_002_000,
        )
        self.assertEqual(r1.conversation_type, "unknown")
        first = self.db.recent_messages(1)[0]
        self.assertIsNone(first["person_id"])

        r2 = self.ingestor.ingest_batch(
            "小雨",
            [("her", None, "在")],
            1_700_000_003_000,
        )
        self.assertEqual(r2.conversation_type, "private")
        rows = self.db.recent_messages(10)
        self.assertTrue(all(row["person_id"] for row in rows))

class TestRealtimePipeline(unittest.TestCase):
    def setUp(self):
        from chatweight.db import ChatWeightDb
        from chatweight.wechat_live import WeChatSqliteIngestor, private_person_id_for
        self.tmp=tempfile.TemporaryDirectory()
        self.db_path=Path(self.tmp.name)/'chatweight.db'
        self.db=ChatWeightDb(self.db_path,ROOT/'sql'/'schema.sql')
        self.ing=WeChatSqliteIngestor(self.db)
        self.private_person_id_for=private_person_id_for
    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def test_live_messages_create_weight_state_and_snapshot(self):
        base=1_700_000_100_000
        self.ing.ingest_batch('小雨',[('her',None,'在吗'),('me',None,'在呀')],base)
        pid=self.private_person_id_for('小雨')
        n=self.db.conn.execute('SELECT COUNT(*) FROM weight_events WHERE person_id=?',(pid,)).fetchone()[0]
        self.assertGreater(n,0)
        n2=self.db.conn.execute('SELECT COUNT(*) FROM daily_weight_snapshots WHERE person_id=?',(pid,)).fetchone()[0]
        self.assertEqual(n2,2)

    def test_crush_auto_relationship_event_updates_profile(self):
        from chatweight.models import RelationshipType
        base=1_700_000_200_000
        self.ing.ingest_batch('小雨',[('her',None,'你好')],base)
        pid=self.private_person_id_for('小雨')
        self.db.set_relationship_type(pid,RelationshipType.CRUSH,base)
        self.ing.ingest_batch('小雨',[('me',None,'今天突然有点想你了')],base+60_000)
        prof=self.db.get_relationship_profile(pid,base+60_000)
        self.assertGreater(prof.expression_raw,0)
        applied=self.db.conn.execute("SELECT COUNT(*) FROM relationship_events WHERE person_id=? AND event_type='light_missing_expression'",(pid,)).fetchone()[0]
        self.assertEqual(applied,1)

    def test_direct_like_goes_to_review_and_does_not_apply(self):
        from chatweight.models import RelationshipType
        base=1_700_000_300_000
        self.ing.ingest_batch('小雨',[('her',None,'你好')],base)
        pid=self.private_person_id_for('小雨')
        self.db.set_relationship_type(pid,RelationshipType.CRUSH,base)
        before=self.db.get_relationship_profile(pid,base).expression_raw
        self.ing.ingest_batch('小雨',[('me',None,'其实我挺喜欢你的')],base+60_000)
        row=self.db.conn.execute("SELECT * FROM relationship_event_candidates WHERE person_id=? AND event_type='direct_like_expression'",(pid,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['status'],'pending')
        after=self.db.get_relationship_profile(pid,base+60_000).expression_raw
        self.assertEqual(before,after)

    def test_restart_restores_session_without_new_start(self):
        from chatweight.wechat_live import WeChatSqliteIngestor, private_person_id_for
        base=1_700_000_400_000
        self.ing.ingest_batch('小雨',[('her',None,'第一条')],base)
        pid=private_person_id_for('小雨')
        starts1=self.db.conn.execute("SELECT COUNT(*) FROM weight_events WHERE person_id=? AND event_type='session_start'",(pid,)).fetchone()[0]
        ing2=WeChatSqliteIngestor(self.db)
        ing2.ingest_batch('小雨',[('me',None,'继续聊')],base+5*60_000)
        starts2=self.db.conn.execute("SELECT COUNT(*) FROM weight_events WHERE person_id=? AND event_type='session_start'",(pid,)).fetchone()[0]
        self.assertEqual(starts1,starts2)

class TestManualReviewFlow(unittest.TestCase):
    def test_confirm_direct_like_applies_stage_gate(self):
        from chatweight.db import ChatWeightDb
        from chatweight.wechat_live import WeChatSqliteIngestor, private_person_id_for
        from chatweight.pipeline import RealtimeAnalysisPipeline
        from chatweight.models import RelationshipType, ExpressionStage
        with tempfile.TemporaryDirectory() as td:
            db=ChatWeightDb(Path(td)/'c.db',ROOT/'sql'/'schema.sql')
            try:
                ing=WeChatSqliteIngestor(db); base=1_700_001_000_000
                ing.ingest_batch('小雨',[('her',None,'你好')],base)
                pid=private_person_id_for('小雨'); db.set_relationship_type(pid,RelationshipType.CRUSH,base)
                ing.ingest_batch('小雨',[('me',None,'其实我挺喜欢你的')],base+60_000)
                row=db.conn.execute("SELECT id FROM relationship_event_candidates WHERE person_id=? AND event_type='direct_like_expression'",(pid,)).fetchone()
                self.assertTrue(RealtimeAnalysisPipeline(db).confirm_candidate(row['id']))
                prof=db.get_relationship_profile(pid,base+60_000)
                self.assertEqual(prof.expression_stage,ExpressionStage.DIRECT_EXPRESSION)
            finally: db.close()
