"""Local outbox table + dispatcher: how a producing service avoids losing
events on crash.

A domain write and its "to-publish" event are inserted into the SAME local
SQLite transaction, in this service's own outbox table. A background
dispatcher thread separately polls pending rows and calls EventLog.Append,
marking each row published only after the remote call succeeds. If the
process crashes between the domain write and the publish, the row is still
sitting in the outbox and gets picked up on the next poll — the event is
never silently dropped, at the cost of at-least-once delivery (hence the
producer_dedupe_key on Append).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from services.event_log.client import EventLogClient
from shared.safety import redact_payload

logger = logging.getLogger("outbox")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status);
"""


def ensure_outbox_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


def enqueue(conn: sqlite3.Connection, topic: str, correlation_id: str, event_type: str, payload: dict) -> str:
    """Call this inside the same transaction as the domain write it accompanies."""
    outbox_id = f"obx_{uuid.uuid4().hex[:16]}"
    conn.execute(
        "INSERT INTO outbox(id, topic, correlation_id, event_type, payload_json, created_at_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (outbox_id, topic, correlation_id, event_type, json.dumps(redact_payload(payload)), int(time.time() * 1000)),
    )
    return outbox_id


class OutboxDispatcher:
    """Polls a service's local outbox and publishes pending rows to the event log."""

    def __init__(self, db_path: Path, event_log_client: EventLogClient | None = None, poll_interval_s: float = 0.2):
        self._db_path = db_path
        self._client = event_log_client or EventLogClient()
        self._poll_interval_s = poll_interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        while not self._stop.is_set():
            self.dispatch_once(conn)
            time.sleep(self._poll_interval_s)

    def dispatch_once(self, conn: sqlite3.Connection) -> int:
        rows = conn.execute(
            "SELECT id, topic, correlation_id, event_type, payload_json FROM outbox "
            "WHERE status = 'pending' ORDER BY created_at_ms ASC LIMIT 50"
        ).fetchall()
        published = 0
        for outbox_id, topic, correlation_id, event_type, payload_json in rows:
            try:
                self._client.append(
                    topic=topic,
                    correlation_id=correlation_id,
                    event_type=event_type,
                    payload=json.loads(payload_json),
                    producer_dedupe_key=outbox_id,
                )
                conn.execute("UPDATE outbox SET status = 'published' WHERE id = ?", (outbox_id,))
                conn.commit()
                published += 1
            except Exception:
                logger.exception("failed to dispatch outbox row %s, will retry", outbox_id)
                conn.execute("UPDATE outbox SET attempts = attempts + 1 WHERE id = ?", (outbox_id,))
                conn.commit()
        return published
