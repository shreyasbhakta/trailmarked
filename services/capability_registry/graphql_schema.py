"""Dashboard's read layer only — one query nests a capability, its version
history, recent runs, and each run's event timeline without over- or
under-fetching. Never used for writes; those go through gRPC/REST.
"""
from __future__ import annotations

import json

import strawberry

from services.capability_registry.store import RegistryStore

_store = RegistryStore()


@strawberry.type
class EventEntry:
    topic: str
    offset: int
    event_type: str
    occurred_at_ms: float
    payload_json: str


@strawberry.type
class RunSummary:
    run_id: str
    kind: str
    tenant_id: str | None
    correlation_id: str
    status: str
    started_at_ms: float

    @strawberry.field
    def timeline(self) -> list[EventEntry]:
        return [
            EventEntry(
                topic=e["topic"], offset=e["offset"], event_type=e["event_type"],
                occurred_at_ms=e["occurred_at_ms"], payload_json=json.dumps(e["payload"]),
            )
            for e in _store.run_timeline(self.run_id)
        ]


@strawberry.type
class CapabilityVersion:
    version: int
    compatibility: str
    discovery_run_id: str
    compiled_at_ms: float
    last_validated_at_ms: float | None
    consecutive_hard_failures: int
    confidence: str


@strawberry.type
class Capability:
    capability_id: str
    latest_version: int

    @strawberry.field
    def versions(self) -> list[CapabilityVersion]:
        return [
            CapabilityVersion(
                version=v["version"], compatibility=v["compatibility"], discovery_run_id=v["discovery_run_id"],
                compiled_at_ms=v["compiled_at_ms"], last_validated_at_ms=v["last_validated_at_ms"],
                consecutive_hard_failures=v["consecutive_hard_failures"], confidence=v["confidence"],
            )
            for v in _store.version_history(self.capability_id)
        ]

    @strawberry.field
    def artifact_json(self, version: int = 0) -> str:
        row = _store.get_version(self.capability_id, version, "*") if version else _store.latest_version(self.capability_id, "*")
        return row["artifact_json"] if row else "{}"

    @strawberry.field
    def recent_runs(self, limit: int = 20) -> list[RunSummary]:
        return [
            RunSummary(run_id=r["run_id"], kind=r["kind"], tenant_id=r["tenant_id"], correlation_id=r["correlation_id"], status=r["status"], started_at_ms=r["started_at_ms"])
            for r in _store.recent_runs(self.capability_id, limit)
        ]


@strawberry.type
class Query:
    @strawberry.field
    def capabilities(self) -> list[Capability]:
        return [Capability(capability_id=c["capability_id"], latest_version=c["latest_version"]) for c in _store.list_capabilities()]

    @strawberry.field
    def capability(self, capability_id: str) -> Capability | None:
        row = _store.latest_version(capability_id, "*")
        if not row:
            return None
        return Capability(capability_id=capability_id, latest_version=row["version"])

    @strawberry.field
    def run(self, run_id: str) -> RunSummary | None:
        row = _store.get_run(run_id)
        if not row:
            return None
        return RunSummary(run_id=row["run_id"], kind=row["kind"], tenant_id=row["tenant_id"], correlation_id=row["correlation_id"], status=row["status"], started_at_ms=row["started_at_ms"])


schema = strawberry.Schema(query=Query)
