"""Escalation saga state: AGENT_CONTROLLED -> INTERVENTION_REQUESTED ->
HUMAN_CONTROLLED -> CONTROL_RETURNED -> (RESUMED | TERMINATED).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "escalation_saga.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sagas (
    saga_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'AGENT_CONTROLLED',
    dead_letter_event_id TEXT,
    context_json TEXT NOT NULL DEFAULT '{}',
    claimed_by_operator_id TEXT,
    session_handle TEXT,
    created_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS human_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    saga_id TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    action_json TEXT NOT NULL,
    occurred_at_ms INTEGER NOT NULL
);
"""


class SagaStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def create(self, saga_id: str, run_id: str, correlation_id: str, dead_letter_event_id: str, context: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO sagas(saga_id, run_id, correlation_id, status, dead_letter_event_id, context_json, created_at_ms) "
                "VALUES (?, ?, ?, 'INTERVENTION_REQUESTED', ?, ?, ?)",
                (saga_id, run_id, correlation_id, dead_letter_event_id, json.dumps(context), int(time.time() * 1000)),
            )
            self._conn.commit()

    def claim(self, saga_id: str, operator_id: str, session_handle: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sagas SET status = 'HUMAN_CONTROLLED', claimed_by_operator_id = ?, session_handle = ? WHERE saga_id = ?",
                (operator_id, session_handle, saga_id),
            )
            self._conn.commit()

    def record_human_action(self, saga_id: str, operator_id: str, action: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO human_actions(saga_id, operator_id, action_json, occurred_at_ms) VALUES (?, ?, ?, ?)",
                (saga_id, operator_id, json.dumps(action), int(time.time() * 1000)),
            )
            self._conn.commit()

    def release(self, saga_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE sagas SET status = ? WHERE saga_id = ?", (status, saga_id))
            self._conn.commit()

    def list_all(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT saga_id, run_id, status, claimed_by_operator_id FROM sagas ORDER BY created_at_ms DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [{"saga_id": r[0], "run_id": r[1], "status": r[2], "claimed_by_operator_id": r[3]} for r in rows]

    def get(self, saga_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT saga_id, run_id, status, claimed_by_operator_id, session_handle, context_json, "
                "dead_letter_event_id, correlation_id FROM sagas WHERE saga_id = ?",
                (saga_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "saga_id": row[0], "run_id": row[1], "status": row[2], "claimed_by_operator_id": row[3],
                "session_handle": row[4], "context": json.loads(row[5]), "dead_letter_event_id": row[6],
                "correlation_id": row[7],
            }
