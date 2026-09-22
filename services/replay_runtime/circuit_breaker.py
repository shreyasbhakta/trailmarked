"""Circuit breaker around the target-app driver, keyed by (tenant_id,
capability_id). After N consecutive run-level failures it trips open and
fails fast for a cooldown window, rather than letting every replay hammer a
production banking UI that's already down.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "replay_runtime.db"

FAILURE_THRESHOLD = 3
COOLDOWN_S = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS circuit_breakers (
    target_key TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'CLOSED',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    cooldown_until_ms INTEGER NOT NULL DEFAULT 0
);
"""


class CircuitOpenError(Exception):
    def __init__(self, target_key: str, cooldown_until_ms: int):
        super().__init__(f"circuit open for {target_key} until {cooldown_until_ms}")
        self.target_key = target_key
        self.cooldown_until_ms = cooldown_until_ms


class CircuitBreaker:
    def __init__(self, db_path: Path = DB_PATH):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _get(self, target_key: str) -> tuple[str, int, int]:
        row = self._conn.execute(
            "SELECT state, consecutive_failures, cooldown_until_ms FROM circuit_breakers WHERE target_key = ?",
            (target_key,),
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO circuit_breakers(target_key) VALUES (?)", (target_key,)
            )
            self._conn.commit()
            return "CLOSED", 0, 0
        return row

    def before_run(self, target_key: str) -> None:
        """Raises CircuitOpenError if the breaker is open and still cooling down."""
        with self._lock:
            state, failures, cooldown_until_ms = self._get(target_key)
            now_ms = int(time.time() * 1000)
            if state == "OPEN":
                if now_ms < cooldown_until_ms:
                    raise CircuitOpenError(target_key, cooldown_until_ms)
                self._conn.execute(
                    "UPDATE circuit_breakers SET state = 'HALF_OPEN' WHERE target_key = ?", (target_key,)
                )
                self._conn.commit()

    def record_success(self, target_key: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE circuit_breakers SET state = 'CLOSED', consecutive_failures = 0 WHERE target_key = ?",
                (target_key,),
            )
            self._conn.commit()

    def record_failure(self, target_key: str) -> None:
        with self._lock:
            _, failures, _ = self._get(target_key)
            failures += 1
            if failures >= FAILURE_THRESHOLD:
                cooldown_until_ms = int(time.time() * 1000) + COOLDOWN_S * 1000
                self._conn.execute(
                    "UPDATE circuit_breakers SET state = 'OPEN', consecutive_failures = ?, cooldown_until_ms = ? "
                    "WHERE target_key = ?",
                    (failures, cooldown_until_ms, target_key),
                )
            else:
                self._conn.execute(
                    "UPDATE circuit_breakers SET consecutive_failures = ? WHERE target_key = ?",
                    (failures, target_key),
                )
            self._conn.commit()

    def state(self, target_key: str) -> dict:
        with self._lock:
            state, failures, cooldown_until_ms = self._get(target_key)
            return {"state": state, "consecutive_failures": failures, "cooldown_until_ms": cooldown_until_ms}
