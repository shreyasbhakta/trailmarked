"""Agent-facing capability invocation API. Deliberately REST/JSON rather
than gRPC: external agent tooling (function-calling, OpenAPI schemas) is
built around REST, so this is a compatibility decision at the platform's
one true external-agent boundary, not a default we reached for out of habit.
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from services.capability_registry.client import CapabilityRegistryClient
from services.escalation_saga.client import EscalationSagaClient
from services.replay_runtime.client import ReplayRuntimeClient
from shared.correlation import new_correlation_id
from shared.rate_limit import RateLimitExceeded, RateLimiter

app = FastAPI(title="Trailmarked Capability API")

_registry = CapabilityRegistryClient()
_replay = ReplayRuntimeClient()
_escalation = EscalationSagaClient()
_rate_limiter = RateLimiter()


class InvokeRequest(BaseModel):
    tenant_id: str = "default"
    input_params: dict = {}
    idempotency_key: str | None = None
    version: int = 0


class InvokeResponse(BaseModel):
    run_id: str
    deduplicated: bool
    correlation_id: str


@app.get("/capabilities")
def list_capabilities():
    return {"capabilities": _registry.list_capabilities()}


@app.get("/capabilities/{capability_id}")
def get_capability(capability_id: str, version: int = 0):
    try:
        return _registry.get_capability(capability_id, version)
    except Exception as exc:  # noqa: BLE001 - surfaced as 404 to the caller
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/capabilities/{capability_id}/invoke", response_model=InvokeResponse)
def invoke_capability(capability_id: str, body: InvokeRequest):
    try:
        _rate_limiter.check(capability_id, body.tenant_id)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    correlation_id = new_correlation_id()
    idempotency_key = body.idempotency_key or f"idem_{uuid.uuid4().hex[:16]}"

    ack = _replay.submit_replay(
        capability_id=capability_id,
        tenant_id=body.tenant_id,
        idempotency_key=idempotency_key,
        input_params=body.input_params,
        correlation_id=correlation_id,
        version=body.version,
    )
    return InvokeResponse(run_id=ack["run_id"], deduplicated=ack["deduplicated"], correlation_id=correlation_id)


@app.get("/capabilities/{capability_id}/runs/{run_id}")
def get_run_status(capability_id: str, run_id: str):
    return _replay.get_status(run_id)


@app.get("/circuit-breaker/{tenant_id}/{capability_id}")
def get_circuit_breaker(tenant_id: str, capability_id: str):
    return _replay.get_circuit_breaker_state(f"{tenant_id}:{capability_id}")


class ClaimRequest(BaseModel):
    operator_id: str


class ActRequest(BaseModel):
    operator_id: str
    action_type: str
    locator: str
    value: str = ""


class ReleaseRequest(BaseModel):
    operator_id: str
    resume_agent: bool = False


@app.get("/escalations")
def list_escalations():
    return {"sagas": _escalation.list_sagas()}


@app.get("/escalations/{saga_id}")
def get_escalation(saga_id: str):
    try:
        return _escalation.get_saga_state(saga_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/escalations/{saga_id}/claim")
def claim_escalation(saga_id: str, body: ClaimRequest):
    return _escalation.claim_session(saga_id, body.operator_id)


@app.post("/escalations/{saga_id}/act")
def act_on_escalation(saga_id: str, body: ActRequest):
    _escalation.record_human_action(saga_id, body.operator_id, {"action_type": body.action_type, "locator": body.locator, "value": body.value})
    return {"ok": True}


@app.post("/escalations/{saga_id}/release")
def release_escalation(saga_id: str, body: ReleaseRequest):
    return _escalation.release_control(saga_id, body.operator_id, body.resume_agent)
