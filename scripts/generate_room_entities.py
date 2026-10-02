"""Generate Room entities from the shared SQLite schema.

Run from the repository root with: python scripts/generate_room_entities.py
The generated file is checked in so Android builds do not need Python.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "sql" / "schema.sql"
OUTPUT = (
    ROOT
    / "android-app/app/src/main/java/io/chatweight/android/database/entity/RoomEntities.kt"
)

NAMES = {
    "persons": "PersonEntity",
    "platform_identities": "PlatformIdentityEntity",
    "conversations": "ConversationEntity",
    "messages": "MessageEntity",
    "chat_sessions": "ChatSessionEntity",
    "weight_events": "WeightEventEntity",
    "weight_state": "WeightStateEntity",
    "daily_metrics": "DailyMetricsEntity",
    "daily_weight_snapshots": "DailyWeightSnapshotEntity",
    "relationship_profile": "RelationshipProfileEntity",
    "relationship_events": "RelationshipEventEntity",
    "relationship_daily_snapshot": "RelationshipDailySnapshotEntity",
    "algorithm_meta": "AlgorithmMetaEntity",
    "relationship_event_candidates": "RelationshipEventCandidateEntity",
    "person_special_nicknames": "PersonSpecialNicknameEntity",
}

# Extra Android indexes for foreign keys not covered by the shared schema's
# query indexes. They do not change field meaning or uniqueness.
ROOM_FK_INDEXES = {
    "conversations": [("idx_conversations_primary_person_room", False, ["primary_person_id"])],
    "relationship_events": [("idx_relationship_events_conversation_room", False, ["conversation_id"])],
}


def camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.title() for part in tail)


def generate() -> str:
    sql = SCHEMA.read_text(encoding="utf-8")
    indices: dict[str, list[tuple[str, bool, list[str]]]] = {}
    index_pattern = re.compile(
        r"CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+ON\s+(\w+)\s*\(([^)]+)\)",
        re.I | re.S,
    )
    for match in index_pattern.finditer(sql):
        unique, name, table, fields = match.groups()
        indices.setdefault(table, []).append(
            (name, bool(unique), [part.strip() for part in fields.split(",")])
        )

    out = [
        "package io.chatweight.android.database.entity",
        "",
        "import androidx.room.ColumnInfo",
        "import androidx.room.Entity",
        "import androidx.room.ForeignKey",
        "import androidx.room.Index",
        "",
        "// Generated from sql/schema.sql. Edit that schema and rerun scripts/generate_room_entities.py.",
    ]
    table_pattern = re.compile(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.*?)\);", re.I | re.S)
    for match in table_pattern.finditer(sql):
        table, body = match.groups()
        if table not in NAMES:
            raise ValueError(f"Unmapped table: {table}")
        columns: list[tuple[str, str, bool]] = []
        primary: list[str] = []
        fks: list[tuple[str, str, str, str]] = []
        for raw in body.splitlines():
            line = raw.strip().rstrip(",")
            col = re.match(r"^(\w+)\s+(TEXT|INTEGER|REAL)\b(.*)$", line, re.I)
            if col:
                name, kind, rest = col.groups()
                columns.append((name, kind.upper(), "NOT NULL" in rest.upper()))
                if "PRIMARY KEY" in rest.upper():
                    primary = [name]
                continue
            pk = re.match(r"PRIMARY KEY\(([^)]+)\)", line, re.I)
            if pk:
                primary = [x.strip() for x in pk.group(1).split(",")]
                continue
            fk = re.match(
                r"FOREIGN KEY\((\w+)\) REFERENCES (\w+)\((\w+)\) ON DELETE (CASCADE|SET NULL)",
                line,
                re.I,
            )
            if fk:
                fks.append(fk.groups())
        if not columns or not primary:
            raise ValueError(f"Cannot map table {table}")
        args = [f'tableName = "{table}"', "primaryKeys = [" + ", ".join(f'"{x}"' for x in primary) + "]"]
        if fks:
            fk_expr = []
            for child, parent, parent_col, action in fks:
                parent_class = NAMES[parent]
                action_expr = "CASCADE" if action.upper() == "CASCADE" else "SET_NULL"
                fk_expr.append(
                    f'ForeignKey(entity = {parent_class}::class, parentColumns = ["{parent_col}"], '
                    f'childColumns = ["{child}"], onDelete = ForeignKey.{action_expr})'
                )
            args.append("foreignKeys = [" + ", ".join(fk_expr) + "]")
        table_indices = indices.get(table, []) + ROOM_FK_INDEXES.get(table, [])
        if table_indices:
            idx_expr = []
            for name, unique, fields in table_indices:
                fields_expr = ", ".join(f'"{x}"' for x in fields)
                idx_expr.append(
                    f'Index(value = [{fields_expr}], name = "{name}", unique = {str(unique).lower()})'
                )
            args.append("indices = [" + ", ".join(idx_expr) + "]")
        out.append("@Entity(\n    " + ",\n    ".join(args) + "\n)")
        out.append(f"data class {NAMES[table]}(")
        for name, kind, required in columns:
            kt_type = {"TEXT": "String", "INTEGER": "Long", "REAL": "Double"}[kind]
            default = {"TEXT": '""', "INTEGER": "0L", "REAL": "0.0"}[kind]
            if not required and name not in primary:
                kt_type += "?"
                default = "null"
            out.append(f'    @ColumnInfo(name = "{name}") val {camel(name)}: {kt_type} = {default},')
        out.append(")")
        out.append("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(generate(), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
