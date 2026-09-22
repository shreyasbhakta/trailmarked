"""SQLite-backed append-only log: topics, per-topic offsets, consumer-group
checkpoints, and a dead-letter table. This file is owned exclusively by the
event_log service — every other service reaches it only through gRPC.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(__file__).parent / "event_log.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    offset INTEGER NOT NULL,
    correlation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    producer_dedupe_key TEXT,
    UNIQUE(topic, offset)
);
CREATE INDEX IF NOT EXISTS idx_events_topic_offset ON events(topic, offset);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedupe ON events(topic, producer_dedupe_key)
    WHERE producer_dedupe_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS topic_offsets (
    topic TEXT PRIMARY KEY,
    next_offset INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS consumer_offsets (
    topic TEXT NOT NULL,
    consumer_group TEXT NOT NULL,
    committed_offset INTEGER NOT NULL,
    PRIMARY KEY (topic, consumer_group)
);

CREATE TABLE IF NOT EXISTS dead_letters (
    event_id TEXT PRIMARY KEY,
    source_topic TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    failure_reason TEXT NOT NULL,
    original_payload_json TEXT NOT NULL,
    failure_context_json TEXT NOT NULL,
    occurred_at_ms INTEGER NOT NULL
);
"""


@dataclass
class StoredEvent:
    event_id: str
    topic: str
    offset: int
    correlation_id: str
    event_type: str
    occurred_at_ms: int
    payload_json: str


class EventStore:
    """Thread-safe wrapper around the SQLite log. One connection per thread,
    guarded by a lock, is sufficient at this scale and keeps the "append is
    atomic and offsets are gapless per topic" invariant simple to reason about.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def append(
        self,
        topic: str,
        correlation_id: str,
        event_type: str,
        payload_json: bytes,
        producer_dedupe_key: str | None,
    ) -> tuple[str, int]:
        with self._lock:
            cur = self._conn.cursor()
            if producer_dedupe_key:
                existing = cur.execute(
                    "SELECT event_id, offset FROM events WHERE topic = ? AND producer_dedupe_key = ?",
                    (topic, producer_dedupe_key),
                ).fetchone()
                if existing:
                    return existing[0], existing[1]

            cur.execute(
                "INSERT INTO topic_offsets(topic, next_offset) VALUES (?, 0) "
                "ON CONFLICT(topic) DO NOTHING",
                (topic,),
            )
            row = cur.execute(
                "UPDATE topic_offsets SET next_offset = next_offset + 1 WHERE topic = ? "
                "RETURNING next_offset - 1",
                (topic,),
            ).fetchone()
            offset = row[0]
            event_id = f"evt_{uuid.uuid4().hex[:16]}"
            occurred_at_ms = int(time.time() * 1000)
            cur.execute(
                "INSERT INTO events(event_id, topic, offset, correlation_id, event_type, "
                "occurred_at_ms, payload_json, producer_dedupe_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    topic,
                    offset,
                    correlation_id,
                    event_type,
                    occurred_at_ms,
                    payload_json.decode("utf-8"),
                    producer_dedupe_key,
                ),
            )
            self._conn.commit()
            return event_id, offset

    def fetch(self, topic: str, consumer_group: str, max_events: int) -> list[StoredEvent]:
        with self._lock:
            cur = self._conn.cursor()
            committed = cur.execute(
                "SELECT committed_offset FROM consumer_offsets WHERE topic = ? AND consumer_group = ?",
                (topic, consumer_group),
            ).fetchone()
            start_offset = (committed[0] + 1) if committed else 0
            rows = cur.execute(
                "SELECT event_id, topic, offset, correlation_id, event_type, occurred_at_ms, payload_json "
                "FROM events WHERE topic = ? AND offset >= ? ORDER BY offset ASC LIMIT ?",
                (topic, start_offset, max_events),
            ).fetchall()
            return [StoredEvent(*row) for row in rows]

    def fetch_from(self, topic: str, from_offset: int, max_events: int = 1000) -> list[StoredEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT event_id, topic, offset, correlation_id, event_type, occurred_at_ms, payload_json "
                "FROM events WHERE topic = ? AND offset >= ? ORDER BY offset ASC LIMIT ?",
                (topic, from_offset, max_events),
            ).fetchall()
            return [StoredEvent(*row) for row in rows]

    def commit_offset(self, topic: str, consumer_group: str, offset: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO consumer_offsets(topic, consumer_group, committed_offset) VALUES (?, ?, ?) "
                "ON CONFLICT(topic, consumer_group) DO UPDATE SET committed_offset = excluded.committed_offset",
                (topic, consumer_group, offset),
            )
            self._conn.commit()

    def dead_letter(
        self,
        source_topic: str,
        correlation_id: str,
        failure_reason: str,
        original_payload_json: bytes,
        failure_context_json: bytes,
    ) -> str:
        with self._lock:
            event_id = f"dlq_{uuid.uuid4().hex[:16]}"
            self._conn.execute(
                "INSERT INTO dead_letters(event_id, source_topic, correlation_id, failure_reason, "
                "original_payload_json, failure_context_json, occurred_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    source_topic,
                    correlation_id,
                    failure_reason,
                    original_payload_json.decode("utf-8"),
                    failure_context_json.decode("utf-8"),
                    int(time.time() * 1000),
                ),
            )
            self._conn.commit()
            return event_id

    def latest_offset(self, topic: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT next_offset - 1 FROM topic_offsets WHERE topic = ?", (topic,)
            ).fetchone()
            return row[0] if row else -1
