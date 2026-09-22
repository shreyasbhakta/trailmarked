"""Consumer group that projects discovery/replay/escalation events into the
registry's read-model tables (runs, run_events). This is the CQRS read side
GraphQL queries — it never reads the event log directly.
"""
from __future__ import annotations

import json
import logging
import threading
import time

from services.capability_registry.store import RegistryStore
from services.event_log.client import EventLogClient

logger = logging.getLogger("capability_registry.projector")

CONSUMER_GROUP = "registry-projector"
TOPICS = ("discovery.events", "replay.events", "escalation.events")
POLL_INTERVAL_S = 0.5

_RUN_KIND_BY_TOPIC = {"discovery.events": "discovery", "replay.events": "replay", "escalation.events": "escalation"}
_TERMINAL_STATUS_EVENTS = {
    "RunSucceeded": "SUCCEEDED", "RunFailed": "FAILED",
    "ReplaySucceeded": "SUCCEEDED", "ReplayHardFailure": "HARD_FAILURE",
}
_VALIDATION_OUTCOME_BY_EVENT = {"ReplaySucceeded": "BUSINESS_OUTCOME", "ReplayHardFailure": "HARD_FAILURE"}


def _run_id_for(topic: str, payload: dict) -> str | None:
    return payload.get("run_id")


class Projector:
    def __init__(self, store: RegistryStore, event_log: EventLogClient | None = None):
        self._store = store
        self._event_log = event_log or EventLogClient()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            for topic in TOPICS:
                self.project_once(topic)
            time.sleep(POLL_INTERVAL_S)

    def project_once(self, topic: str) -> int:
        events = self._event_log.fetch(topic, CONSUMER_GROUP, max_events=200)
        for event in events:
            run_id = _run_id_for(topic, event.payload)
            if run_id:
                self._store.upsert_run(
                    run_id=run_id,
                    kind=_RUN_KIND_BY_TOPIC[topic],
                    capability_id=event.payload.get("capability_id"),
                    tenant_id=event.payload.get("tenant_id"),
                    correlation_id=event.correlation_id,
                    started_at_ms=event.occurred_at_ms,
                )
                self._store.append_run_event(run_id, topic, event.offset, event.event_type, event.occurred_at_ms, json.dumps(event.payload))
                if event.event_type in _TERMINAL_STATUS_EVENTS:
                    self._store.set_run_status(run_id, _TERMINAL_STATUS_EVENTS[event.event_type])
                if event.event_type in _VALIDATION_OUTCOME_BY_EVENT:
                    capability_id = event.payload.get("capability_id")
                    version = event.payload.get("version")
                    if capability_id and version:
                        self._store.record_validation(
                            capability_id=capability_id, version=version, tenant_scope="*",
                            outcome=_VALIDATION_OUTCOME_BY_EVENT[event.event_type],
                        )
            if events:
                self._event_log.commit_offset(topic, CONSUMER_GROUP, event.offset)
        return len(events)
