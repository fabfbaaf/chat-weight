PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS persons (
    id TEXT PRIMARY KEY NOT NULL,
    display_name TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_identities (
    id TEXT PRIMARY KEY NOT NULL,
    person_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    platform_user_id TEXT,
    display_name TEXT,
    alias TEXT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_identity_person ON platform_identities(person_id);
CREATE INDEX IF NOT EXISTS idx_identity_platform_user ON platform_identities(platform, platform_user_id);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY NOT NULL,
    platform TEXT NOT NULL,
    platform_conversation_id TEXT,
    title TEXT,
    conversation_type TEXT NOT NULL,
    primary_person_id TEXT,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    FOREIGN KEY(primary_person_id) REFERENCES persons(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY NOT NULL,
    platform TEXT NOT NULL,
    account_id TEXT,
    conversation_id TEXT NOT NULL,
    person_id TEXT,
    sender_id TEXT,
    sender_name TEXT,
    direction TEXT NOT NULL,
    message_type TEXT NOT NULL,
    text TEXT,
    message_time INTEGER NOT NULL,
    captured_at INTEGER NOT NULL,
    voice_duration_ms INTEGER,
    reply_to_message_id TEXT,
    fingerprint TEXT NOT NULL,
    capture_source TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    raw_json TEXT,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_time ON messages(conversation_id, message_time);
CREATE INDEX IF NOT EXISTS idx_messages_person_time ON messages(person_id, message_time);
CREATE INDEX IF NOT EXISTS idx_messages_direction_time ON messages(conversation_id, direction, message_time);
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_fingerprint ON messages(platform, conversation_id, fingerprint);

CREATE TABLE IF NOT EXISTS qq_proactive_attempts (
    id TEXT PRIMARY KEY NOT NULL,
    account_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    attempted_at INTEGER NOT NULL,
    status TEXT NOT NULL,
    topic TEXT,
    text TEXT,
    onebot_message_id TEXT,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    UNIQUE(account_id, user_id, local_date)
);
CREATE INDEX IF NOT EXISTS idx_qq_proactive_friend_time ON qq_proactive_attempts(account_id, user_id, attempted_at);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY NOT NULL,
    conversation_id TEXT NOT NULL,
    primary_person_id TEXT,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    initiator_side TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    incoming_count INTEGER NOT NULL DEFAULT 0,
    outgoing_count INTEGER NOT NULL DEFAULT 0,
    turn_count INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    last_message_at INTEGER NOT NULL,
    close_reason TEXT,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_conversation_start ON chat_sessions(conversation_id, started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_person_start ON chat_sessions(primary_person_id, started_at);

CREATE TABLE IF NOT EXISTS weight_events (
    id TEXT PRIMARY KEY NOT NULL,
    person_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    session_id TEXT,
    actor_side TEXT NOT NULL,
    event_type TEXT NOT NULL,
    dimension TEXT NOT NULL,
    base_delta REAL NOT NULL,
    repeat_multiplier REAL NOT NULL DEFAULT 1.0,
    confidence_multiplier REAL NOT NULL DEFAULT 1.0,
    cap_multiplier REAL NOT NULL DEFAULT 1.0,
    effective_delta REAL NOT NULL,
    event_time INTEGER NOT NULL,
    repeat_group TEXT,
    source_message_ids_json TEXT,
    metadata_json TEXT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_weight_events_person_time ON weight_events(person_id, event_time);
CREATE INDEX IF NOT EXISTS idx_weight_events_person_dimension ON weight_events(person_id, actor_side, dimension, event_time);
CREATE INDEX IF NOT EXISTS idx_weight_events_session ON weight_events(session_id, event_type);

CREATE TABLE IF NOT EXISTS weight_state (
    person_id TEXT NOT NULL,
    actor_side TEXT NOT NULL,
    dimension TEXT NOT NULL,
    recent_raw REAL NOT NULL DEFAULT 0,
    base_raw REAL NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(person_id, actor_side, dimension),
    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    person_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    incoming_messages INTEGER NOT NULL DEFAULT 0,
    outgoing_messages INTEGER NOT NULL DEFAULT 0,
    incoming_chars INTEGER NOT NULL DEFAULT 0,
    outgoing_chars INTEGER NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 0,
    self_started_sessions INTEGER NOT NULL DEFAULT 0,
    other_started_sessions INTEGER NOT NULL DEFAULT 0,
    total_turns INTEGER NOT NULL DEFAULT 0,
    self_avg_reply_ms INTEGER,
    other_avg_reply_ms INTEGER,
    active_minutes INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(person_id, local_date)
);

CREATE TABLE IF NOT EXISTS daily_weight_snapshots (
    person_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    actor_side TEXT NOT NULL,
    initiative_score REAL NOT NULL,
    response_score REAL NOT NULL,
    effort_score REAL NOT NULL,
    continuity_score REAL NOT NULL,
    frequency_score REAL NOT NULL,
    overall_score REAL NOT NULL,
    recent_raw_total REAL NOT NULL,
    base_raw_total REAL NOT NULL,
    confidence_score REAL NOT NULL,
    calculated_at INTEGER NOT NULL,
    PRIMARY KEY(person_id, local_date, actor_side)
);

CREATE TABLE IF NOT EXISTS relationship_profile (
    person_id TEXT PRIMARY KEY NOT NULL,
    relationship_type TEXT NOT NULL,
    custom_label TEXT,
    expression_stage INTEGER NOT NULL DEFAULT 0,
    highest_expression_stage INTEGER NOT NULL DEFAULT 0,
    expression_raw REAL NOT NULL DEFAULT 0,
    expression_heat_raw REAL NOT NULL DEFAULT 0,
    heat_updated_at INTEGER NOT NULL,
    manually_confirmed_stage INTEGER,
    last_relationship_event_at INTEGER,
    engine_version INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relationship_events (
    id TEXT PRIMARY KEY NOT NULL,
    person_id TEXT NOT NULL,
    conversation_id TEXT,
    session_id TEXT,
    actor_side TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_category TEXT NOT NULL,
    source TEXT NOT NULL,
    base_progress_delta REAL NOT NULL,
    base_heat_delta REAL NOT NULL,
    repeat_multiplier REAL NOT NULL DEFAULT 1.0,
    confidence REAL NOT NULL DEFAULT 1.0,
    effective_progress_delta REAL NOT NULL,
    effective_heat_delta REAL NOT NULL,
    event_time INTEGER NOT NULL,
    source_message_ids_json TEXT,
    metadata_json TEXT,
    dedupe_key TEXT,
    engine_version INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_relationship_events_person_time ON relationship_events(person_id, event_time);
CREATE INDEX IF NOT EXISTS idx_relationship_events_person_type ON relationship_events(person_id, event_type, event_time);
CREATE INDEX IF NOT EXISTS idx_relationship_events_category ON relationship_events(person_id, event_category, event_time);
CREATE INDEX IF NOT EXISTS idx_relationship_events_session ON relationship_events(session_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_relationship_events_dedupe ON relationship_events(person_id, dedupe_key) WHERE dedupe_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS relationship_daily_snapshot (
    person_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    expression_stage INTEGER NOT NULL,
    highest_expression_stage INTEGER NOT NULL,
    expression_raw REAL NOT NULL,
    expression_progress_score REAL NOT NULL,
    expression_heat_raw REAL NOT NULL,
    expression_heat_score REAL NOT NULL,
    familiarity_event_count INTEGER NOT NULL DEFAULT 0,
    approach_event_count INTEGER NOT NULL DEFAULT 0,
    care_event_count INTEGER NOT NULL DEFAULT 0,
    affection_event_count INTEGER NOT NULL DEFAULT 0,
    direct_expression_count INTEGER NOT NULL DEFAULT 0,
    retreat_event_count INTEGER NOT NULL DEFAULT 0,
    valid_session_count INTEGER NOT NULL DEFAULT 0,
    calculated_at INTEGER NOT NULL,
    engine_version INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(person_id, local_date),
    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS algorithm_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO algorithm_meta(key, value) VALUES ('schema_version', '1');
INSERT OR IGNORE INTO algorithm_meta(key, value) VALUES ('weight_rule_version', '1');
INSERT OR IGNORE INTO algorithm_meta(key, value) VALUES ('relationship_engine_version', '1');

CREATE TABLE IF NOT EXISTS relationship_event_candidates (
    id TEXT PRIMARY KEY NOT NULL,
    person_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    session_id TEXT,
    actor_side TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    confirmation_policy TEXT NOT NULL,
    status TEXT NOT NULL,
    event_time INTEGER NOT NULL,
    source_message_ids_json TEXT,
    evidence_text TEXT,
    reason_code TEXT,
    metadata_json TEXT,
    dedupe_key TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    reviewed_at INTEGER,
    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_relationship_candidates_dedupe
ON relationship_event_candidates(person_id, dedupe_key);
CREATE INDEX IF NOT EXISTS idx_relationship_candidates_pending
ON relationship_event_candidates(status, event_time);

CREATE TABLE IF NOT EXISTS person_special_nicknames (
    person_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY(person_id, nickname),
    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE
);

INSERT OR REPLACE INTO algorithm_meta(key, value) VALUES ('schema_version', '2');
