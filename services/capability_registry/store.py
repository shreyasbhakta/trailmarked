"""Capability Registry's own storage: the read side of CQRS. capabilities/
tenant_overlays are written directly by the compiler; runs/run_events are a
projection kept in sync by projector.py consuming the event log — this table
is what the GraphQL layer reads, never the event log directly.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "registry.db"

# A version whose most recent replays keep hard-failing has drifted from the
# live app it was recorded against; past this many failures in a row it's
# no longer safe to trust unattended, regardless of how long ago it was
# last proven to work.
HARD_FAILURE_CONFIDENCE_THRESHOLD = 2


def _confidence(last_validated_at_ms: int | None, consecutive_hard_failures: int) -> str:
    if last_validated_at_ms is None or consecutive_hard_failures >= HARD_FAILURE_CONFIDENCE_THRESHOLD:
        return "NEEDS_REVIEW"
    return "FRESH"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS capabilities (
    capability_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    tenant_scope TEXT NOT NULL,
    compatibility TEXT NOT NULL,
    artifact_json TEXT NOT NULL,
    discovery_run_id TEXT NOT NULL,
    compiled_at_ms INTEGER NOT NULL,
    last_validated_at_ms INTEGER,
    consecutive_hard_failures INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (capability_id, version, tenant_scope)
);

CREATE TABLE IF NOT EXISTS tenant_overlays (
    tenant_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    overlay_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, capability_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    capability_id TEXT,
    tenant_id TEXT,
    correlation_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
    started_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS run_events (
    run_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    offset INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (topic, offset)
);
CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id);

CREATE TABLE IF NOT EXISTS projector_offsets (
    topic TEXT PRIMARY KEY,
    next_offset INTEGER NOT NULL DEFAULT 0
);
"""


class RegistryStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate_confidence_columns()
        self._conn.commit()

    def _migrate_confidence_columns(self) -> None:
        # CREATE TABLE IF NOT EXISTS doesn't add columns to a table that
        # already existed under the old schema, so a plain-old dev database
        # needs an explicit, idempotent column add.
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(capabilities)")}
        if "last_validated_at_ms" not in existing:
            self._conn.execute("ALTER TABLE capabilities ADD COLUMN last_validated_at_ms INTEGER")
        if "consecutive_hard_failures" not in existing:
            self._conn.execute("ALTER TABLE capabilities ADD COLUMN consecutive_hard_failures INTEGER NOT NULL DEFAULT 0")

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def latest_version(self, capability_id: str, tenant_scope: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT version, compatibility, artifact_json, discovery_run_id, compiled_at_ms, "
                "last_validated_at_ms, consecutive_hard_failures FROM capabilities "
                "WHERE capability_id = ? AND tenant_scope = ? ORDER BY version DESC LIMIT 1",
                (capability_id, tenant_scope),
            ).fetchone()
            if not row:
                return None
            return {
                "version": row[0],
                "compatibility": row[1],
                "artifact_json": row[2],
                "discovery_run_id": row[3],
                "compiled_at_ms": row[4],
                "last_validated_at_ms": row[5],
                "consecutive_hard_failures": row[6],
                "confidence": _confidence(row[5], row[6]),
            }

    def insert_version(
        self,
        capability_id: str,
        version: int,
        tenant_scope: str,
        compatibility: str,
        artifact_json: str,
        discovery_run_id: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO capabilities(capability_id, version, tenant_scope, compatibility, artifact_json, "
                "discovery_run_id, compiled_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (capability_id, version, tenant_scope, compatibility, artifact_json, discovery_run_id, int(time.time() * 1000)),
            )
            self._conn.commit()

    def get_version(self, capability_id: str, version: int, tenant_scope: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT version, compatibility, artifact_json, discovery_run_id, compiled_at_ms, "
                "last_validated_at_ms, consecutive_hard_failures FROM capabilities "
                "WHERE capability_id = ? AND version = ? AND tenant_scope = ?",
                (capability_id, version, tenant_scope),
            ).fetchone()
            if not row:
                return None
            return {
                "version": row[0],
                "compatibility": row[1],
                "artifact_json": row[2],
                "discovery_run_id": row[3],
                "compiled_at_ms": row[4],
                "last_validated_at_ms": row[5],
                "consecutive_hard_failures": row[6],
                "confidence": _confidence(row[5], row[6]),
            }

    def version_history(self, capability_id: str, tenant_scope: str = "*") -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT version, compatibility, discovery_run_id, compiled_at_ms, "
                "last_validated_at_ms, consecutive_hard_failures FROM capabilities "
                "WHERE capability_id = ? AND tenant_scope = ? ORDER BY version ASC",
                (capability_id, tenant_scope),
            ).fetchall()
            return [
                {
                    "version": r[0], "compatibility": r[1], "discovery_run_id": r[2], "compiled_at_ms": r[3],
                    "last_validated_at_ms": r[4], "consecutive_hard_failures": r[5], "confidence": _confidence(r[4], r[5]),
                }
                for r in rows
            ]

    def record_validation(self, capability_id: str, version: int, tenant_scope: str, outcome: str) -> None:
        """Called by the projector as it consumes ReplaySucceeded/ReplayHardFailure
        off the event log — this is how a capability's confidence tracks its
        actual recent replay history instead of just how it looked at compile time.
        """
        with self._lock:
            if outcome == "BUSINESS_OUTCOME":
                self._conn.execute(
                    "UPDATE capabilities SET last_validated_at_ms = ?, consecutive_hard_failures = 0 "
                    "WHERE capability_id = ? AND version = ? AND tenant_scope = ?",
                    (int(time.time() * 1000), capability_id, version, tenant_scope),
                )
            elif outcome == "HARD_FAILURE":
                self._conn.execute(
                    "UPDATE capabilities SET consecutive_hard_failures = consecutive_hard_failures + 1 "
                    "WHERE capability_id = ? AND version = ? AND tenant_scope = ?",
                    (capability_id, version, tenant_scope),
                )
            self._conn.commit()

    def list_capabilities(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT capability_id, MAX(version) FROM capabilities WHERE tenant_scope = '*' GROUP BY capability_id"
            ).fetchall()
            return [{"capability_id": r[0], "latest_version": r[1]} for r in rows]

    def get_overlay(self, tenant_id: str, capability_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT overlay_json FROM tenant_overlays WHERE tenant_id = ? AND capability_id = ?",
                (tenant_id, capability_id),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def put_overlay(self, tenant_id: str, capability_id: str, overlay_json: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO tenant_overlays(tenant_id, capability_id, overlay_json) VALUES (?, ?, ?) "
                "ON CONFLICT(tenant_id, capability_id) DO UPDATE SET overlay_json = excluded.overlay_json",
                (tenant_id, capability_id, overlay_json),
            )
            self._conn.commit()

    # --- projection tables, written by projector.py -----------------------

    def upsert_run(self, run_id: str, kind: str, capability_id: str | None, tenant_id: str | None, correlation_id: str, started_at_ms: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs(run_id, kind, capability_id, tenant_id, correlation_id, started_at_ms) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(run_id) DO NOTHING",
                (run_id, kind, capability_id, tenant_id, correlation_id, started_at_ms),
            )
            self._conn.commit()

    def set_run_status(self, run_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id))
            self._conn.commit()

    def append_run_event(self, run_id: str, topic: str, offset: int, event_type: str, occurred_at_ms: int, payload_json: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO run_events(run_id, topic, offset, event_type, occurred_at_ms, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(topic, offset) DO NOTHING",
                (run_id, topic, offset, event_type, occurred_at_ms, payload_json),
            )
            self._conn.commit()

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT run_id, kind, capability_id, tenant_id, correlation_id, status, started_at_ms FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "run_id": row[0], "kind": row[1], "capability_id": row[2], "tenant_id": row[3],
                "correlation_id": row[4], "status": row[5], "started_at_ms": row[6],
            }

    def recent_runs(self, capability_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT run_id, kind, tenant_id, correlation_id, status, started_at_ms FROM runs "
                "WHERE capability_id = ? ORDER BY started_at_ms DESC LIMIT ?",
                (capability_id, limit),
            ).fetchall()
            return [
                {"run_id": r[0], "kind": r[1], "tenant_id": r[2], "correlation_id": r[3], "status": r[4], "started_at_ms": r[5]}
                for r in rows
            ]

    def run_timeline(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT topic, offset, event_type, occurred_at_ms, payload_json FROM run_events "
                "WHERE run_id = ? ORDER BY occurred_at_ms ASC",
                (run_id,),
            ).fetchall()
            return [
                {"topic": r[0], "offset": r[1], "event_type": r[2], "occurred_at_ms": r[3], "payload": json.loads(r[4])}
                for r in rows
            ]

    def get_projector_offset(self, topic: str) -> int:
        with self._lock:
            row = self._conn.execute("SELECT next_offset FROM projector_offsets WHERE topic = ?", (topic,)).fetchone()
            return row[0] if row else 0

    def set_projector_offset(self, topic: str, next_offset: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO projector_offsets(topic, next_offset) VALUES (?, ?) "
                "ON CONFLICT(topic) DO UPDATE SET next_offset = excluded.next_offset",
                (topic, next_offset),
            )
            self._conn.commit()
