"""Replay-run persistence: idempotency-key lookups and run status, sharing
the replay_runtime.db file the circuit breaker also lives in.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "replay_runtime.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS replay_runs (
    run_id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    capability_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    tenant_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'PENDING',
    outputs_json TEXT NOT NULL DEFAULT '{}',
    retry_count INTEGER NOT NULL DEFAULT 0,
    failed_step_id TEXT,
    dead_letter_event_id TEXT,
    started_at_ms INTEGER NOT NULL
);
"""


class ReplayStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def find_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT run_id, outcome, outputs_json FROM replay_runs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if not row:
                return None
            return {"run_id": row[0], "outcome": row[1], "outputs": json.loads(row[2])}

    def create_pending(self, run_id: str, idempotency_key: str, capability_id: str, version: int, tenant_id: str, correlation_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO replay_runs(run_id, idempotency_key, capability_id, version, tenant_id, correlation_id, started_at_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, idempotency_key, capability_id, version, tenant_id, correlation_id, int(time.time() * 1000)),
            )
            self._conn.commit()

    def complete(self, run_id: str, outcome: str, outputs: dict, retry_count: int, failed_step_id: str | None, dead_letter_event_id: str | None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE replay_runs SET outcome = ?, outputs_json = ?, retry_count = ?, failed_step_id = ?, "
                "dead_letter_event_id = ? WHERE run_id = ?",
                (outcome, json.dumps(outputs), retry_count, failed_step_id, dead_letter_event_id, run_id),
            )
            self._conn.commit()

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT run_id, outcome, outputs_json, retry_count, failed_step_id, dead_letter_event_id FROM replay_runs "
                "WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "run_id": row[0], "outcome": row[1], "outputs": json.loads(row[2]),
                "retry_count": row[3], "failed_step_id": row[4], "dead_letter_event_id": row[5],
            }
