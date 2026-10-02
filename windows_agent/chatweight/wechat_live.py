from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import queue
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .db import ChatWeightDb
from .models import MessageDirection, MessageType, Platform, UnifiedMessage
from .session import SessionManager
from .pipeline import RealtimeAnalysisPipeline

_CAPTURE_SOURCE = "jev_windows_wgc_rapidocr"


def _slug_hash(value: str, n: int = 24) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()[:n]


def conversation_id_for(title: str) -> str:
    return f"wechat:win:conversation:{_slug_hash(title)}"


def private_person_id_for(title: str) -> str:
    # OCR exposes only the visible chat title, not a stable wxid. Keep this ID
    # platform-scoped and deterministic, but never claim it is an official ID.
    return f"wechat:win:person:{_slug_hash(title)}"


def group_member_person_id_for(title: str, sender_name: str) -> str:
    # Do NOT merge same display names across groups: OCR gives no stable wxid.
    return f"wechat:win:group-member:{_slug_hash(title + chr(0) + sender_name)}"


def identity_id_for(person_id: str) -> str:
    return f"identity:{_slug_hash(person_id)}"


@dataclass(slots=True)
class IngestResult:
    inserted: int
    duplicates: int
    conversation_id: str
    conversation_type: str


class WeChatSqliteIngestor:
    """Normalize Jev OCR tuples and persist them as ChatWeight messages."""

    def __init__(self, db: ChatWeightDb, *, account_id: str = "wechat-windows-local") -> None:
        self.db = db
        self.account_id = account_id
        self.sessions = SessionManager()
        self.pipeline = RealtimeAnalysisPipeline(db)

    def _ensure_person(self, person_id: str, display_name: str, now_ms: int) -> None:
        self.db.create_person(person_id, display_name, now_ms)
        self.db.create_platform_identity(
            identity_id_for(person_id),
            person_id,
            Platform.WECHAT.value,
            display_name,
            now_ms,
            platform_user_id=None,
            alias=display_name,
        )

    def _classify_conversation(self, title: str, lines: list[tuple[str, str | None, str]], now_ms: int):
        cid = conversation_id_for(title)
        existing = self.db.conversation(cid)
        existing_type = existing["conversation_type"] if existing else "unknown"
        existing_primary = existing["primary_person_id"] if existing else None

        has_named_incoming = any(who == "her" and name for who, name, _ in lines)
        has_unnamed_incoming = any(who == "her" and not name for who, name, _ in lines)

        if has_named_incoming:
            kind = "group"
            primary = None
        elif existing_type == "group":
            kind = "group"
            primary = None
        elif has_unnamed_incoming:
            kind = "private"
            primary = existing_primary or private_person_id_for(title)
            self._ensure_person(primary, title, now_ms)
        elif existing_type == "private":
            kind = "private"
            primary = existing_primary or private_person_id_for(title)
            self._ensure_person(primary, title, now_ms)
        else:
            kind = "unknown"
            primary = None

        self.db.create_conversation(
            cid,
            Platform.WECHAT.value,
            primary,
            now_ms,
            title=title,
            conversation_type=kind,
            platform_conversation_id=None,
        )
        if kind in {"private", "group"}:
            self.db.set_conversation_kind(cid, kind, now_ms, primary)
        return cid, kind, primary

    def ingest_batch(
        self,
        title: str,
        lines: Iterable[tuple[str, str | None, str]],
        captured_at_ms: int | None = None,
    ) -> IngestResult:
        now_ms = int(captured_at_ms or time.time() * 1000)
        clean_lines = [(w, n, (t or "").strip()) for w, n, t in lines if (t or "").strip()]
        cid, kind, primary = self._classify_conversation(title, clean_lines, now_ms)

        inserted = duplicates = 0
        for index, (who, name, text) in enumerate(clean_lines):
            direction = MessageDirection.OUTGOING if who == "me" else MessageDirection.INCOMING
            person_id: str | None = None
            sender_id: str | None = None
            sender_name: str | None = None

            if kind == "group":
                if direction == MessageDirection.INCOMING and name:
                    person_id = group_member_person_id_for(title, name)
                    sender_id = person_id
                    sender_name = name
                    self._ensure_person(person_id, name, now_ms)
                elif direction == MessageDirection.OUTGOING:
                    sender_id = "self"
                    sender_name = "我"
            elif kind == "private":
                person_id = primary
                if direction == MessageDirection.INCOMING:
                    sender_id = primary
                    sender_name = title
                else:
                    sender_id = "self"
                    sender_name = "我"
            else:
                # An outgoing-only first batch cannot prove whether this is a group.
                # Store it now; if a later incoming line proves this is private,
                # set_conversation_kind() backfills NULL person_id rows.
                if direction == MessageDirection.OUTGOING:
                    sender_id = "self"
                    sender_name = "我"

            observed_ms = now_ms + index
            fingerprint_source = "\x1f".join(
                [cid, direction.value, sender_name or "", text, str(now_ms // 1000), str(index)]
            )
            fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
            message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"chatweight:{fingerprint}"))
            raw_json = json.dumps(
                {
                    "source": _CAPTURE_SOURCE,
                    "wechat_title": title,
                    "ocr_who": who,
                    "ocr_sender_name": name,
                    "observed_at_ms": observed_ms,
                    "timestamp_semantics": "capture_observed_time_not_wechat_original_send_time",
                },
                ensure_ascii=False,
            )
            message = UnifiedMessage(
                id=message_id,
                platform=Platform.WECHAT,
                account_id=self.account_id,
                conversation_id=cid,
                person_id=person_id,
                sender_id=sender_id,
                sender_name=sender_name,
                direction=direction,
                message_type=MessageType.TEXT,
                text=text,
                message_time=observed_ms,
                captured_at=observed_ms,
                fingerprint=fingerprint,
                capture_source=_CAPTURE_SOURCE,
                confidence=0.90,
                raw_json=raw_json,
            )
            if self.db.insert_message(message):
                inserted += 1
                if message.conversation_id not in self.sessions.current:
                    restored = self.db.load_recent_session(message.conversation_id, message.message_time)
                    if restored is not None:
                        self.sessions.current[message.conversation_id] = restored
                session, is_new_session = self.sessions.ingest(message)
                if session.person_id is None and message.person_id is not None:
                    session.person_id = message.person_id
                self.db.upsert_session(session)
                self.pipeline.process(message, session, is_new_session)
            else:
                duplicates += 1

        return IngestResult(inserted, duplicates, cid, kind)


class WeChatLiveRecorder:
    """Run Jev's WGC/OCR capture subprocess and stream new lines into SQLite."""

    def __init__(
        self,
        db_path: str | Path,
        schema_path: str | Path,
        *,
        prime_existing: bool = True,
        account_id: str = "wechat-windows-local",
    ) -> None:
        self.db_path = Path(db_path)
        self.schema_path = Path(schema_path)
        self.prime_existing = prime_existing
        self.account_id = account_id
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run_forever(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("微信实时采集只能在 Windows 10/11 上运行")

        from .jev_windows.capture import find_wechat_hwnd
        from .jev_windows.worker import run as capture_worker

        hwnd = find_wechat_hwnd()
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        enabled = ctx.Event()
        enabled.set()
        proc = ctx.Process(
            target=capture_worker,
            args=(q, hwnd, enabled, self.prime_existing),
            name="chatweight-wechat-capture",
            daemon=True,
        )
        proc.start()

        db = ChatWeightDb(self.db_path, self.schema_path)
        ingestor = WeChatSqliteIngestor(db, account_id=self.account_id)
        print(f"[ChatWeight] DB: {self.db_path}")
        print("[ChatWeight] 微信采集已启动。首次看到每个会话时只预热，不回灌屏幕上的旧消息。")
        print("[ChatWeight] 按 Ctrl+C 停止。")

        try:
            while not self._stop:
                try:
                    item = q.get(timeout=0.5)
                except queue.Empty:
                    if not proc.is_alive():
                        raise RuntimeError("微信采集子进程已经退出")
                    continue

                kind = item[0]
                if kind == "lines":
                    _, title, lines, ts_ms = item
                    result = ingestor.ingest_batch(title, lines, ts_ms)
                    if result.inserted:
                        print(
                            f"[{title}] +{result.inserted} 条 -> SQLite "
                            f"({result.conversation_type}, total={db.message_count()})"
                        )
                        for who, name, text in lines:
                            speaker = "我" if who == "me" else (name or title)
                            print(f"  {speaker}: {text}")
                elif kind == "chat":
                    print(f"[ChatWeight] 当前会话: {item[1]}")
                elif kind == "status":
                    print(f"[ChatWeight] 采集状态: {item[1]}")
                elif kind == "dead":
                    raise RuntimeError(item[1])
        except KeyboardInterrupt:
            pass
        finally:
            enabled.clear()
            self._stop = True
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=3)
            db.close()
            print("[ChatWeight] 已停止。")


def _default_schema() -> Path:
    return Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChatWeight Windows 微信实时采集 -> SQLite")
    parser.add_argument("--db", default="chatweight.db", help="SQLite database path")
    parser.add_argument("--schema", default=str(_default_schema()), help="schema.sql path")
    parser.add_argument(
        "--backfill-visible-on-first-frame",
        action="store_true",
        help="启动/首次切到会话时把当前屏幕可见消息也写入（默认关闭，避免重复旧消息）",
    )
    args = parser.parse_args(argv)

    recorder = WeChatLiveRecorder(
        args.db,
        args.schema,
        prime_existing=not args.backfill_visible_on_first_frame,
    )
    recorder.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
