"""Domain event and capability artifact schemas.

These are the payloads carried inside event_log.Event.payload_json and
registry.Capability.artifact_json. Proto keeps those fields opaque so each
schema can evolve independently of the gRPC transport; this module is the
actual source of truth for shape and validation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Discovery-run domain events (write side)
# ---------------------------------------------------------------------------

class RiskTag(str, Enum):
    SAFE = "safe"
    RISKY = "risky"


class DomainEventType(str, Enum):
    OBSERVATION_CAPTURED = "ObservationCaptured"
    ACTION_DECIDED = "ActionDecided"
    ACTION_EXECUTED = "ActionExecuted"
    ACTION_BLOCKED = "ActionBlocked"
    STEP_SUCCEEDED = "StepSucceeded"
    STEP_FAILED = "StepFailed"
    RUN_SUCCEEDED = "RunSucceeded"
    RUN_FAILED = "RunFailed"
    REPLAY_REQUESTED = "ReplayRequested"
    REPLAY_STEP_EXECUTED = "ReplayStepExecuted"
    REPLAY_SUCCEEDED = "ReplaySucceeded"
    REPLAY_RECOVERABLE_RETRY = "ReplayRecoverableRetry"
    REPLAY_HARD_FAILURE = "ReplayHardFailure"
    INTERVENTION_REQUESTED = "InterventionRequested"
    HUMAN_ACTED = "HumanActed"
    CONTROL_RETURNED = "ControlReturned"


class ObservationCaptured(BaseModel):
    run_id: str
    step_index: int
    a11y_snapshot: str
    url: str
    screenshot_ref: str | None = None


class ActionDecided(BaseModel):
    run_id: str
    step_index: int
    action_type: Literal["click", "fill", "select", "navigate", "assert", "extract"]
    target_description: str
    locator_candidates: list[str]
    params: dict[str, Any] = Field(default_factory=dict)
    risk_tag: RiskTag
    rationale: str
    param_bindings: dict[str, str] = Field(default_factory=dict)


class ActionExecuted(BaseModel):
    run_id: str
    step_index: int
    locator_used: str
    outcome: Literal["success", "error"]
    error_message: str | None = None


class ActionBlocked(BaseModel):
    run_id: str
    step_index: int
    reason: str
    domain: str
    action_type: str


class StepSucceeded(BaseModel):
    run_id: str
    step_index: int
    checkpoint_assertions: list[str] = Field(default_factory=list)


class StepFailed(BaseModel):
    run_id: str
    step_index: int
    reason: str


class RunSucceeded(BaseModel):
    run_id: str
    capability_id: str
    tenant_id: str
    goal: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    success_condition: str = ""


class RunFailed(BaseModel):
    run_id: str
    goal: str
    reason: str


# ---------------------------------------------------------------------------
# Capability artifact ("the trailmark") — read side, denormalized from events
# ---------------------------------------------------------------------------

class Compatibility(str, Enum):
    BACKWARD = "BACKWARD"
    FORWARD = "FORWARD"
    BREAKING = "BREAKING"


class InputParam(BaseModel):
    name: str
    type: Literal["string", "int", "float", "bool"]
    required: bool = True
    description: str = ""


class LocatorStrategy(BaseModel):
    kind: Literal["role", "label", "text", "test_id", "css"]
    value: str


class CapabilityStep(BaseModel):
    step_id: str
    action_type: Literal["click", "fill", "select", "navigate", "assert", "extract"]
    strategy_chain: list[LocatorStrategy]
    risk_tag: RiskTag
    param_bindings: dict[str, str] = Field(default_factory=dict)


class Checkpoint(BaseModel):
    checkpoint_id: str
    step_id: str
    assertion: str  # e.g. "url_contains", "text_present", "element_visible"
    expected: str


class OutputSpec(BaseModel):
    name: str
    type: Literal["string", "int", "float", "bool"]
    extraction_source: str  # step_id + locator this output is read from


class Provenance(BaseModel):
    discovery_run_id: str
    compiled_at: datetime = Field(default_factory=utcnow)


class RiskSummary(BaseModel):
    highest_risk_tag: RiskTag
    risky_step_count: int
    requires_preapproval: bool


class CapabilityArtifact(BaseModel):
    capability_id: str
    version: int
    compatibility: Compatibility
    tenant_scope: str  # "*" for base, else tenant_id
    input_params: list[InputParam]
    steps: list[CapabilityStep]
    checkpoints: list[Checkpoint]
    outputs: list[OutputSpec]
    success_condition: str
    provenance: Provenance
    risk_summary: RiskSummary


class TenantOverlay(BaseModel):
    """Per-tenant override merged onto a base CapabilityArtifact at resolve time."""

    tenant_id: str
    capability_id: str
    locator_overrides: dict[str, list[LocatorStrategy]] = Field(default_factory=dict)
    param_overrides: dict[str, dict[str, str]] = Field(default_factory=dict)
