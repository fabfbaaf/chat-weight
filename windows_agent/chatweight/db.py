from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import ChatSession, RelationshipProfileState, UnifiedMessage


class ChatWeightDb:
    def __init__(self, path: str | Path, schema_path: str | Path | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        if schema_path:
            self.conn.executescript(Path(schema_path).read_text(encoding="utf-8"))
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def create_person(self, person_id: str, display_name: str, now_ms: int) -> None:
        self.conn.execute(
            """INSERT INTO persons(id,display_name,created_at,updated_at) VALUES (?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name, updated_at=excluded.updated_at""",
            (person_id, display_name, now_ms, now_ms),
        )
        self.conn.commit()

    def create_platform_identity(
        self,
        identity_id: str,
        person_id: str,
        platform: str,
        display_name: str,
        now_ms: int,
        platform_user_id: str | None = None,
        alias: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO platform_identities
               (id,person_id,platform,platform_user_id,display_name,alias,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (identity_id, person_id, platform, platform_user_id, display_name, alias, now_ms),
        )
        self.conn.commit()

    def create_conversation(
        self,
        conversation_id: str,
        platform: str,
        person_id: str | None,
        now_ms: int,
        title: str = "",
        conversation_type: str = "unknown",
        platform_conversation_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO conversations
               (id,platform,platform_conversation_id,title,conversation_type,primary_person_id,first_seen_at,last_seen_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title,
                 last_seen_at=excluded.last_seen_at""",
            (
                conversation_id,
                platform,
                platform_conversation_id,
                title,
                conversation_type,
                person_id,
                now_ms,
                now_ms,
            ),
        )
        self.conn.commit()

    def set_conversation_kind(
        self,
        conversation_id: str,
        conversation_type: str,
        now_ms: int,
        primary_person_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """UPDATE conversations SET
                 conversation_type=?,
                 primary_person_id=COALESCE(?, primary_person_id),
                 last_seen_at=?
               WHERE id=?""",
            (conversation_type, primary_person_id, now_ms, conversation_id),
        )
        if conversation_type == "private" and primary_person_id:
            # Early outgoing OCR lines may have been stored before the first incoming
            # line proved this is a private chat. Backfill only NULL person_id rows.
            self.conn.execute(
                "UPDATE messages SET person_id=? WHERE conversation_id=? AND person_id IS NULL",
                (primary_person_id, conversation_id),
            )
        self.conn.commit()

    def conversation(self, conversation_id: str):
        return self.conn.execute(
            "SELECT * FROM conversations WHERE id=?", (conversation_id,)
        ).fetchone()

    def insert_message(self, m: UnifiedMessage) -> bool:
        try:
            self.conn.execute(
                """INSERT INTO messages
                (id,platform,account_id,conversation_id,person_id,sender_id,sender_name,direction,message_type,text,
                 message_time,captured_at,voice_duration_ms,reply_to_message_id,fingerprint,capture_source,confidence,raw_json)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    m.id,
                    m.platform.value,
                    m.account_id,
                    m.conversation_id,
                    m.person_id,
                    m.sender_id,
                    m.sender_name,
                    m.direction.value,
                    m.message_type.value,
                    m.text,
                    m.message_time,
                    m.captured_at,
                    m.voice_duration_ms,
                    m.reply_to_message_id,
                    m.fingerprint,
                    m.capture_source,
                    m.confidence,
                    m.raw_json,
                ),
            )
            self.conn.execute(
                "UPDATE conversations SET last_seen_at=? WHERE id=?",
                (m.captured_at, m.conversation_id),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False

    def upsert_session(self, s: ChatSession) -> None:
        self.conn.execute(
            """INSERT INTO chat_sessions
               (id,conversation_id,primary_person_id,started_at,ended_at,initiator_side,message_count,
                incoming_count,outgoing_count,turn_count,duration_ms,last_message_at,close_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 primary_person_id=excluded.primary_person_id,
                 ended_at=excluded.ended_at,
                 message_count=excluded.message_count,
                 incoming_count=excluded.incoming_count,
                 outgoing_count=excluded.outgoing_count,
                 turn_count=excluded.turn_count,
                 duration_ms=excluded.duration_ms,
                 last_message_at=excluded.last_message_at""",
            (
                s.id,
                s.conversation_id,
                s.person_id,
                s.started_at,
                s.ended_at,
                s.initiator_side.value,
                s.message_count,
                s.incoming_count,
                s.outgoing_count,
                s.turn_count,
                s.duration_ms,
                s.last_message_at,
                None,
            ),
        )
        self.conn.commit()

    def message_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])

    def recent_messages(self, limit: int = 20):
        return self.conn.execute(
            """SELECT m.*, c.title AS conversation_title
               FROM messages m JOIN conversations c ON c.id=m.conversation_id
               ORDER BY m.captured_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    def upsert_relationship_profile(self, p: RelationshipProfileState, now_ms: int) -> None:
        self.conn.execute(
            """INSERT INTO relationship_profile
            (person_id,relationship_type,custom_label,expression_stage,highest_expression_stage,expression_raw,
             expression_heat_raw,heat_updated_at,manually_confirmed_stage,last_relationship_event_at,engine_version,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(person_id) DO UPDATE SET
              relationship_type=excluded.relationship_type,
              custom_label=excluded.custom_label,
              expression_stage=excluded.expression_stage,
              highest_expression_stage=excluded.highest_expression_stage,
              expression_raw=excluded.expression_raw,
              expression_heat_raw=excluded.expression_heat_raw,
              heat_updated_at=excluded.heat_updated_at,
              manually_confirmed_stage=excluded.manually_confirmed_stage,
              last_relationship_event_at=excluded.last_relationship_event_at,
              updated_at=excluded.updated_at""",
            (
                p.person_id,
                p.relationship_type.value,
                p.custom_label,
                int(p.expression_stage),
                int(p.highest_expression_stage),
                p.expression_raw,
                p.expression_heat_raw,
                p.heat_updated_at,
                int(p.manually_confirmed_stage) if p.manually_confirmed_stage is not None else None,
                p.last_relationship_event_at,
                1,
                now_ms,
                p.updated_at,
            ),
        )
        self.conn.commit()

    def insert_relationship_event(self, candidate, rule, repeat_mult: float = 1.0) -> None:
        progress = rule.progress_delta * repeat_mult * candidate.confidence
        heat = rule.heat_delta * repeat_mult * candidate.confidence
        dedupe_key = f"{candidate.event_type.value}:{','.join(candidate.source_message_ids)}"
        try:
            self.conn.execute(
                """INSERT INTO relationship_events
                (id,person_id,conversation_id,session_id,actor_side,event_type,event_category,source,
                 base_progress_delta,base_heat_delta,repeat_multiplier,confidence,effective_progress_delta,
                 effective_heat_delta,event_time,source_message_ids_json,metadata_json,dedupe_key,engine_version,created_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    candidate.id,
                    candidate.person_id,
                    candidate.conversation_id,
                    candidate.session_id,
                    candidate.actor_side.value,
                    candidate.event_type.value,
                    rule.category.value,
                    candidate.source.value,
                    rule.progress_delta,
                    rule.heat_delta,
                    repeat_mult,
                    candidate.confidence,
                    progress,
                    heat,
                    candidate.event_time,
                    json.dumps(candidate.source_message_ids, ensure_ascii=False),
                    json.dumps(candidate.metadata, ensure_ascii=False),
                    dedupe_key,
                    1,
                    candidate.event_time,
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            self.conn.rollback()

# --- V0.3 realtime analysis persistence helpers ---
from datetime import datetime
from statistics import median
from .models import (
    ActorSide, CandidateStatus, ConfirmationPolicy, DetectionSource,
    DimensionWeightState, ExpressionStage, MessageDirection,
    RelationshipEventCandidate, RelationshipEventType, RelationshipProfileState,
    RelationshipType, WeightDimension,
)


def _row_to_message(row):
    from .models import Platform, MessageType, UnifiedMessage
    if row is None:
        return None
    return UnifiedMessage(
        id=row["id"], platform=Platform(row["platform"]), account_id=row["account_id"],
        conversation_id=row["conversation_id"], person_id=row["person_id"], sender_id=row["sender_id"],
        sender_name=row["sender_name"], direction=MessageDirection(row["direction"]),
        message_type=MessageType(row["message_type"]), text=row["text"], message_time=row["message_time"],
        captured_at=row["captured_at"], voice_duration_ms=row["voice_duration_ms"],
        reply_to_message_id=row["reply_to_message_id"], fingerprint=row["fingerprint"],
        capture_source=row["capture_source"], confidence=row["confidence"], raw_json=row["raw_json"],
    )


def _previous_message(self, conversation_id, current_id):
    row = self.conn.execute(
        """SELECT * FROM messages WHERE conversation_id=? AND id<>? AND message_time <=
           (SELECT message_time FROM messages WHERE id=?) ORDER BY message_time DESC LIMIT 1""",
        (conversation_id, current_id, current_id),
    ).fetchone()
    return _row_to_message(row)


def _messages_before(self, conversation_id, before_ms, limit=8):
    rows = self.conn.execute(
        "SELECT * FROM messages WHERE conversation_id=? AND message_time<? ORDER BY message_time DESC LIMIT ?",
        (conversation_id, before_ms, limit),
    ).fetchall()
    return list(reversed([_row_to_message(r) for r in rows]))


def _median_text_length(self, person_id, days=30, now_ms=None):
    now_ms = now_ms or int(datetime.now().timestamp() * 1000)
    since = now_ms - days * 86_400_000
    vals = [len((r[0] or "").strip()) for r in self.conn.execute(
        "SELECT text FROM messages WHERE person_id=? AND message_type='text' AND message_time>=? AND text IS NOT NULL",
        (person_id, since),
    ).fetchall() if (r[0] or "").strip()]
    return float(median(vals)) if vals else 12.0


def _special_nicknames(self, person_id):
    return {r[0] for r in self.conn.execute(
        "SELECT nickname FROM person_special_nicknames WHERE person_id=?", (person_id,)
    ).fetchall()}


def _weight_event_exists(self, event_id, event_type, source_ids):
    if self.conn.execute("SELECT 1 FROM weight_events WHERE id=?", (event_id,)).fetchone():
        return True
    src = json.dumps(source_ids, ensure_ascii=False)
    return self.conn.execute(
        "SELECT 1 FROM weight_events WHERE event_type=? AND source_message_ids_json=? LIMIT 1", (event_type, src)
    ).fetchone() is not None


def _count_weight_event_in_session(self, session_id, person_id, actor, event_type):
    return int(self.conn.execute(
        "SELECT COUNT(*) FROM weight_events WHERE session_id=? AND person_id=? AND actor_side=? AND event_type=?",
        (session_id, person_id, actor, event_type),
    ).fetchone()[0])


def _count_weight_repeat_group(self, session_id, person_id, actor, repeat_group):
    return int(self.conn.execute(
        "SELECT COUNT(*) FROM weight_events WHERE session_id=? AND person_id=? AND actor_side=? AND repeat_group=?",
        (session_id, person_id, actor, repeat_group),
    ).fetchone()[0])


def _daily_weight_usage(self, person_id, actor, dimension, local_date):
    start = int(datetime.strptime(local_date, "%Y-%m-%d").timestamp() * 1000)
    end = start + 86_400_000
    vals = [float(r[0]) for r in self.conn.execute(
        "SELECT effective_delta FROM weight_events WHERE person_id=? AND actor_side=? AND dimension=? AND event_time>=? AND event_time<?",
        (person_id, actor, dimension, start, end),
    ).fetchall()]
    return sum(v for v in vals if v > 0), sum(v for v in vals if v < 0)


def _get_weight_state(self, person_id, actor, dimension):
    row = self.conn.execute(
        "SELECT * FROM weight_state WHERE person_id=? AND actor_side=? AND dimension=?",
        (person_id, actor.value, dimension.value),
    ).fetchone()
    if not row:
        return DimensionWeightState(person_id, actor, dimension)
    return DimensionWeightState(person_id, actor, dimension, row["recent_raw"], row["base_raw"], row["updated_at"])


def _insert_weight_event(self, event, rule, occurrence, effective_delta):
    mult = 1.0 if occurrence <= 1 or not rule.repeatable else 0.7 if occurrence == 2 else 0.5 if occurrence == 3 else 0.3
    self.conn.execute(
        """INSERT INTO weight_events
        (id,person_id,conversation_id,session_id,actor_side,event_type,dimension,base_delta,repeat_multiplier,
         confidence_multiplier,cap_multiplier,effective_delta,event_time,repeat_group,source_message_ids_json,metadata_json,created_at)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (event.id,event.person_id,event.conversation_id,event.session_id,event.actor.value,event.event_type.value,
         rule.dimension.value,rule.base_delta,mult,event.confidence,1.0,effective_delta,event.event_time,rule.repeat_group,
         json.dumps(event.source_message_ids,ensure_ascii=False),json.dumps(event.metadata,ensure_ascii=False),event.event_time),
    )
    self.conn.commit()


def _upsert_weight_state(self, s):
    self.conn.execute(
        """INSERT INTO weight_state(person_id,actor_side,dimension,recent_raw,base_raw,updated_at) VALUES (?,?,?,?,?,?)
        ON CONFLICT(person_id,actor_side,dimension) DO UPDATE SET recent_raw=excluded.recent_raw,base_raw=excluded.base_raw,updated_at=excluded.updated_at""",
        (s.person_id,s.actor.value,s.dimension.value,s.recent_raw,s.base_raw,s.updated_at),
    )
    self.conn.commit()


def _insert_relationship_candidate(self, c):
    dedupe = f"{c.event_type.value}:{','.join(c.source_message_ids)}"
    try:
        self.conn.execute(
            """INSERT INTO relationship_event_candidates
            (id,person_id,conversation_id,session_id,actor_side,event_type,source,confidence,confirmation_policy,status,event_time,
             source_message_ids_json,evidence_text,reason_code,metadata_json,dedupe_key,created_at)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.id,c.person_id,c.conversation_id,c.session_id,c.actor_side.value,c.event_type.value,c.source.value,c.confidence,
             c.confirmation_policy.value,c.status.value,c.event_time,json.dumps(c.source_message_ids,ensure_ascii=False),
             c.evidence_text,c.reason_code,json.dumps(c.metadata,ensure_ascii=False),dedupe,c.event_time),
        )
        self.conn.commit(); return True
    except sqlite3.IntegrityError:
        self.conn.rollback(); return False


def _load_relationship_candidate(self, cid):
    r = self.conn.execute("SELECT * FROM relationship_event_candidates WHERE id=?", (cid,)).fetchone()
    if not r: return None
    return RelationshipEventCandidate(
        id=r["id"], person_id=r["person_id"], conversation_id=r["conversation_id"], session_id=r["session_id"],
        actor_side=ActorSide(r["actor_side"]), event_type=RelationshipEventType(r["event_type"]), source=DetectionSource(r["source"]),
        confidence=r["confidence"], confirmation_policy=ConfirmationPolicy(r["confirmation_policy"]), status=CandidateStatus(r["status"]),
        event_time=r["event_time"], source_message_ids=json.loads(r["source_message_ids_json"] or "[]"), evidence_text=r["evidence_text"],
        reason_code=r["reason_code"] or "", metadata=json.loads(r["metadata_json"] or "{}"),
    )


def _update_candidate_status(self, cid, status):
    cur = self.conn.execute("UPDATE relationship_event_candidates SET status=?, reviewed_at=? WHERE id=?", (status, int(datetime.now().timestamp()*1000), cid))
    self.conn.commit(); return cur.rowcount > 0


def _count_relationship_event_in_session(self, sid, pid, event_type):
    return int(self.conn.execute("SELECT COUNT(*) FROM relationship_events WHERE session_id=? AND person_id=? AND event_type=?",(sid,pid,event_type)).fetchone()[0])


def _count_relationship_event_on_date(self, pid, event_type, date):
    start=int(datetime.strptime(date,"%Y-%m-%d").timestamp()*1000); end=start+86_400_000
    return int(self.conn.execute("SELECT COUNT(*) FROM relationship_events WHERE person_id=? AND event_type=? AND event_time>=? AND event_time<?",(pid,event_type,start,end)).fetchone()[0])


def _count_relationship_repeat_group(self, sid, pid, repeat_group):
    # event rows do not store repeat_group; derive by matching event types from registry.
    from .rules import RELATIONSHIP_RULES
    types=[t.value for t,r in RELATIONSHIP_RULES.items() if r.repeat_group==repeat_group]
    if not types: return 0
    qs=','.join('?'*len(types))
    return int(self.conn.execute(f"SELECT COUNT(*) FROM relationship_events WHERE session_id=? AND person_id=? AND event_type IN ({qs})",(sid,pid,*types)).fetchone()[0])


def _get_relationship_profile(self, pid, now_ms):
    r=self.conn.execute("SELECT * FROM relationship_profile WHERE person_id=?",(pid,)).fetchone()
    if not r:
        return RelationshipProfileState(person_id=pid, relationship_type=RelationshipType.FRIEND, heat_updated_at=now_ms, updated_at=now_ms)
    return RelationshipProfileState(
        person_id=pid, relationship_type=RelationshipType(r["relationship_type"]), custom_label=r["custom_label"],
        expression_stage=ExpressionStage(r["expression_stage"]), highest_expression_stage=ExpressionStage(r["highest_expression_stage"]),
        expression_raw=r["expression_raw"], expression_heat_raw=r["expression_heat_raw"], heat_updated_at=r["heat_updated_at"],
        manually_confirmed_stage=ExpressionStage(r["manually_confirmed_stage"]) if r["manually_confirmed_stage"] is not None else None,
        last_relationship_event_at=r["last_relationship_event_at"], updated_at=r["updated_at"],
    )


def _set_relationship_type(self, pid, rel_type, now_ms):
    p=self.get_relationship_profile(pid,now_ms); p.relationship_type=rel_type
    self.upsert_relationship_profile(p,now_ms)


def _build_relationship_evidence(self, pid, now_ms, include_candidate=None):
    d30=now_ms-30*86_400_000; d14=now_ms-14*86_400_000
    care={RelationshipEventType.CHECK_IN.value,RelationshipEventType.REMEMBER_AND_FOLLOW_UP.value,RelationshipEventType.EMOTIONAL_SUPPORT.value,
          RelationshipEventType.PRACTICAL_SUPPORT.value,RelationshipEventType.SAFETY_CONCERN.value,RelationshipEventType.SPECIAL_DATE_ATTENTION.value}
    affection={RelationshipEventType.SPECIAL_COMPLIMENT.value,RelationshipEventType.SPECIAL_NICKNAME.value,RelationshipEventType.LIGHT_FLIRT.value,
               RelationshipEventType.LIGHT_MISSING_EXPRESSION.value,RelationshipEventType.CARE_EXPRESSION.value,RelationshipEventType.DEPENDENCY_EXPRESSION.value,
               RelationshipEventType.SPECIAL_IMPORTANCE_EXPRESSION.value}
    direct={RelationshipEventType.DIRECT_LIKE_EXPRESSION.value,RelationshipEventType.DIRECT_ROMANTIC_INTENT.value,RelationshipEventType.PURSUIT_EXPRESSION.value}
    rows=self.conn.execute("SELECT event_type,event_time FROM relationship_events WHERE person_id=? AND event_time>=?",(pid,d30)).fetchall()
    types=[r["event_type"] for r in rows]
    if include_candidate: types.append(include_candidate.event_type.value)
    approach14=sum(1 for r in rows if r["event_time"]>=d14 and r["event_type"] in {
        RelationshipEventType.INITIATE_PRIVATE_CHAT.value,RelationshipEventType.TARGETED_SHARING.value,RelationshipEventType.CONTINUE_CONVERSATION.value,
        RelationshipEventType.INITIATE_VOICE_CALL.value,RelationshipEventType.INITIATE_ACTIVITY.value,RelationshipEventType.INITIATE_MEETUP.value})
    if include_candidate and include_candidate.event_time>=d14 and include_candidate.event_type.value in {
        RelationshipEventType.INITIATE_PRIVATE_CHAT.value,RelationshipEventType.TARGETED_SHARING.value,RelationshipEventType.CONTINUE_CONVERSATION.value,
        RelationshipEventType.INITIATE_VOICE_CALL.value,RelationshipEventType.INITIATE_ACTIVITY.value,RelationshipEventType.INITIATE_MEETUP.value}: approach14+=1
    sessions=int(self.conn.execute("SELECT COUNT(*) FROM chat_sessions WHERE primary_person_id=? AND started_at>=? AND message_count>=2",(pid,d30)).fetchone()[0])
    return {"valid_sessions_30d":sessions,"approach_event_count_14d":approach14,"distinct_care_event_types_30d":len(set(types)&care),
            "has_affection_event":bool(set(types)&affection),"has_direct_expression_event":bool(set(types)&direct),
            "relationship_confirmed":RelationshipEventType.RELATIONSHIP_CONFIRMED.value in types}


def _update_daily_metrics(self, m, session, is_new, previous):
    date=datetime.fromtimestamp(m.message_time/1000).strftime("%Y-%m-%d")
    inc=1 if m.direction==MessageDirection.INCOMING else 0; out=1 if m.direction==MessageDirection.OUTGOING else 0
    chars=len((m.text or "").strip())
    self.conn.execute("""INSERT INTO daily_metrics(person_id,local_date,incoming_messages,outgoing_messages,incoming_chars,outgoing_chars,session_count,self_started_sessions,other_started_sessions,total_turns,active_minutes)
    VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(person_id,local_date) DO UPDATE SET incoming_messages=incoming_messages+excluded.incoming_messages,
    outgoing_messages=outgoing_messages+excluded.outgoing_messages,incoming_chars=incoming_chars+excluded.incoming_chars,outgoing_chars=outgoing_chars+excluded.outgoing_chars,
    session_count=session_count+excluded.session_count,self_started_sessions=self_started_sessions+excluded.self_started_sessions,other_started_sessions=other_started_sessions+excluded.other_started_sessions,
    total_turns=MAX(total_turns,excluded.total_turns),active_minutes=MAX(active_minutes,excluded.active_minutes)""",
    (m.person_id,date,inc,out,chars if inc else 0,chars if out else 0,1 if is_new else 0,1 if is_new and m.actor_side==ActorSide.SELF else 0,
     1 if is_new and m.actor_side==ActorSide.OTHER else 0,session.turn_count,int(session.duration_ms/60000)))
    self.conn.commit()


def _upsert_daily_weight_snapshot(self,pid,date,side,scores,overall,recent_total,base_total,now_ms):
    self.conn.execute("""INSERT INTO daily_weight_snapshots(person_id,local_date,actor_side,initiative_score,response_score,effort_score,continuity_score,frequency_score,overall_score,recent_raw_total,base_raw_total,confidence_score,calculated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(person_id,local_date,actor_side) DO UPDATE SET initiative_score=excluded.initiative_score,response_score=excluded.response_score,
    effort_score=excluded.effort_score,continuity_score=excluded.continuity_score,frequency_score=excluded.frequency_score,overall_score=excluded.overall_score,
    recent_raw_total=excluded.recent_raw_total,base_raw_total=excluded.base_raw_total,confidence_score=excluded.confidence_score,calculated_at=excluded.calculated_at""",
    (pid,date,side.value,scores[WeightDimension.INITIATIVE],scores[WeightDimension.RESPONSE],scores[WeightDimension.EFFORT],scores[WeightDimension.CONTINUITY],
     scores[WeightDimension.FREQUENCY],overall,recent_total,base_total,min(100.0,self.conn.execute("SELECT COUNT(*) FROM chat_sessions WHERE primary_person_id=?",(pid,)).fetchone()[0]*5.0),now_ms))
    self.conn.commit()


def _relationship_category_counts(self,pid,date):
    start=int(datetime.strptime(date,"%Y-%m-%d").timestamp()*1000); end=start+86_400_000
    rows=self.conn.execute("SELECT event_category,COUNT(*) n FROM relationship_events WHERE person_id=? AND event_time>=? AND event_time<? GROUP BY event_category",(pid,start,end)).fetchall()
    return {r["event_category"]:r["n"] for r in rows}


def _valid_session_count(self,pid,date):
    start=int(datetime.strptime(date,"%Y-%m-%d").timestamp()*1000); end=start+86_400_000
    return int(self.conn.execute("SELECT COUNT(*) FROM chat_sessions WHERE primary_person_id=? AND started_at>=? AND started_at<? AND message_count>=2",(pid,start,end)).fetchone()[0])


def _upsert_relationship_daily_snapshot(self,p,date,heat_raw,heat_score,counts,valid_sessions,now_ms):
    self.conn.execute("""INSERT INTO relationship_daily_snapshot(person_id,local_date,relationship_type,expression_stage,highest_expression_stage,expression_raw,expression_progress_score,expression_heat_raw,expression_heat_score,familiarity_event_count,approach_event_count,care_event_count,affection_event_count,direct_expression_count,retreat_event_count,valid_session_count,calculated_at,engine_version)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(person_id,local_date) DO UPDATE SET relationship_type=excluded.relationship_type,expression_stage=excluded.expression_stage,
    highest_expression_stage=excluded.highest_expression_stage,expression_raw=excluded.expression_raw,expression_progress_score=excluded.expression_progress_score,
    expression_heat_raw=excluded.expression_heat_raw,expression_heat_score=excluded.expression_heat_score,familiarity_event_count=excluded.familiarity_event_count,
    approach_event_count=excluded.approach_event_count,care_event_count=excluded.care_event_count,affection_event_count=excluded.affection_event_count,
    direct_expression_count=excluded.direct_expression_count,retreat_event_count=excluded.retreat_event_count,valid_session_count=excluded.valid_session_count,calculated_at=excluded.calculated_at""",
    (p.person_id,date,p.relationship_type.value,int(p.expression_stage),int(p.highest_expression_stage),p.expression_raw,p.expression_raw,heat_raw,heat_score,
     counts.get('familiarity',0),counts.get('approach',0),counts.get('care',0),counts.get('affection',0),counts.get('direct_expression',0),counts.get('retreat',0),valid_sessions,now_ms,1))
    self.conn.commit()


def _pending_candidates(self,limit=50):
    return self.conn.execute("SELECT * FROM relationship_event_candidates WHERE status='pending' ORDER BY event_time DESC LIMIT ?",(limit,)).fetchall()

for _name,_fn in {
    'previous_message':_previous_message,'messages_before':_messages_before,'median_text_length':_median_text_length,'special_nicknames':_special_nicknames,
    'weight_event_exists':_weight_event_exists,'count_weight_event_in_session':_count_weight_event_in_session,'count_weight_repeat_group':_count_weight_repeat_group,
    'daily_weight_usage':_daily_weight_usage,'get_weight_state':_get_weight_state,'insert_weight_event':_insert_weight_event,'upsert_weight_state':_upsert_weight_state,
    'insert_relationship_candidate':_insert_relationship_candidate,'load_relationship_candidate':_load_relationship_candidate,'update_candidate_status':_update_candidate_status,
    'count_relationship_event_in_session':_count_relationship_event_in_session,'count_relationship_event_on_date':_count_relationship_event_on_date,
    'count_relationship_repeat_group':_count_relationship_repeat_group,'get_relationship_profile':_get_relationship_profile,'set_relationship_type':_set_relationship_type,
    'build_relationship_evidence':_build_relationship_evidence,'update_daily_metrics':_update_daily_metrics,'upsert_daily_weight_snapshot':_upsert_daily_weight_snapshot,
    'relationship_category_counts':_relationship_category_counts,'valid_session_count':_valid_session_count,'upsert_relationship_daily_snapshot':_upsert_relationship_daily_snapshot,
    'pending_candidates':_pending_candidates,
}.items():
    setattr(ChatWeightDb,_name,_fn)

def _active_dates(self, pid, now_ms, days=21):
    since=now_ms-days*86_400_000
    rows=self.conn.execute("SELECT DISTINCT local_date FROM daily_metrics WHERE person_id=? AND (incoming_messages+outgoing_messages)>0 AND local_date>=? ORDER BY local_date",(pid,datetime.fromtimestamp(since/1000).strftime('%Y-%m-%d'))).fetchall()
    return [r[0] for r in rows]
ChatWeightDb.active_dates=_active_dates

def _load_recent_session(self, conversation_id, now_ms, gap_ms=30*60*1000):
    from .models import ChatSession
    r=self.conn.execute("SELECT * FROM chat_sessions WHERE conversation_id=? ORDER BY last_message_at DESC LIMIT 1",(conversation_id,)).fetchone()
    if not r or now_ms-r["last_message_at"]>=gap_ms: return None
    last=self.conn.execute("SELECT direction FROM messages WHERE conversation_id=? ORDER BY message_time DESC LIMIT 1",(conversation_id,)).fetchone()
    last_actor=None
    if last:
        if last[0]=='incoming': last_actor=ActorSide.OTHER
        elif last[0]=='outgoing': last_actor=ActorSide.SELF
    return ChatSession(id=r["id"],conversation_id=r["conversation_id"],person_id=r["primary_person_id"],started_at=r["started_at"],ended_at=r["ended_at"],
        initiator_side=ActorSide(r["initiator_side"]),message_count=r["message_count"],incoming_count=r["incoming_count"],outgoing_count=r["outgoing_count"],
        turn_count=r["turn_count"],last_message_at=r["last_message_at"],last_actor_side=last_actor)
ChatWeightDb.load_recent_session=_load_recent_session
