"""Folds a successful discovery run's event stream into a typed
CapabilityArtifact — the "trailmarking" step.
"""
from __future__ import annotations

import uuid

from services.capability_registry.store import RegistryStore
from services.capability_registry.versioning import classify_compatibility
from services.event_log.client import EventLogClient
from shared.schemas import (
    CapabilityArtifact,
    CapabilityStep,
    Checkpoint,
    Compatibility,
    InputParam,
    LocatorStrategy,
    OutputSpec,
    Provenance,
    RiskSummary,
    RiskTag,
)

DISCOVERY_TOPIC = "discovery.events"


def _locator_strategy(candidate: str) -> LocatorStrategy:
    if candidate.startswith("role="):
        return LocatorStrategy(kind="role", value=candidate[len("role="):])
    if candidate.startswith("label="):
        return LocatorStrategy(kind="label", value=candidate[len("label="):])
    if candidate.startswith("text="):
        return LocatorStrategy(kind="text", value=candidate[len("text="):])
    if candidate.startswith("css="):
        return LocatorStrategy(kind="css", value=candidate[len("css="):])
    return LocatorStrategy(kind="css", value=candidate)


def _fetch_run_events(discovery_run_id: str, event_log: EventLogClient) -> list[dict]:
    consumer_group = f"compiler-{uuid.uuid4().hex[:8]}"
    events = event_log.fetch(DISCOVERY_TOPIC, consumer_group, max_events=10_000)
    return sorted(
        (e.payload for e in events if e.payload.get("run_id") == discovery_run_id),
        key=lambda p: p.get("step_index", -1),
    )


def compile_capability(discovery_run_id: str, capability_id: str, tenant_id: str, store: RegistryStore, event_log: EventLogClient | None = None) -> CapabilityArtifact:
    event_log = event_log or EventLogClient()
    events = event_log.fetch(DISCOVERY_TOPIC, f"compiler-{uuid.uuid4().hex[:8]}", max_events=10_000)
    run_events = [e for e in events if e.payload.get("run_id") == discovery_run_id]

    decided_by_step: dict[int, dict] = {}
    executed_by_step: dict[int, dict] = {}
    run_succeeded: dict | None = None

    for event in run_events:
        payload = event.payload
        if event.event_type == "ActionDecided":
            decided_by_step[payload["step_index"]] = payload
        elif event.event_type == "ActionExecuted":
            executed_by_step[payload["step_index"]] = payload
        elif event.event_type == "RunSucceeded":
            run_succeeded = payload

    if run_succeeded is None:
        raise ValueError(f"discovery run {discovery_run_id} has no RunSucceeded event to compile")

    steps: list[CapabilityStep] = []
    checkpoints: list[Checkpoint] = []
    outputs: list[OutputSpec] = []
    input_param_names: set[str] = set()
    risk_tags: list[RiskTag] = []

    for step_index in sorted(decided_by_step):
        decided = decided_by_step[step_index]
        if decided["action_type"] == "finish":
            # The terminal action isn't a replayable step — its outputs are
            # already captured on RunSucceeded and handled separately below.
            continue

        step_id = f"step_{step_index}"
        risk_tag = RiskTag(decided["risk_tag"])
        risk_tags.append(risk_tag)
        input_param_names.update(decided.get("param_bindings", {}).values())

        if decided["action_type"] == "assert":
            checkpoints.append(
                Checkpoint(
                    checkpoint_id=f"chk_{step_index}",
                    step_id=step_id,
                    assertion=decided["params"].get("assertion", ""),
                    expected=str(decided["params"].get("expected", "")),
                )
            )
            # Deliberately falls through to also register the step below —
            # a checkpoint pointing at a step_id that isn't in `steps` would
            # never actually be evaluated during replay.

        if decided["action_type"] == "extract":
            output_name = decided["params"].get("output_name", f"output_{step_index}")
            outputs.append(OutputSpec(name=output_name, type="string", extraction_source=step_id))

        candidates = decided.get("locator_candidates", [])
        executed = executed_by_step.get(step_index)
        if executed and executed.get("locator_used"):
            ordered = [executed["locator_used"]] + [c for c in candidates if c != executed["locator_used"]]
        else:
            ordered = candidates

        steps.append(
            CapabilityStep(
                step_id=step_id,
                action_type=decided["action_type"],
                strategy_chain=[_locator_strategy(c) for c in ordered],
                risk_tag=risk_tag,
                param_bindings=decided.get("param_bindings", {}),
            )
        )

    input_params = [InputParam(name=name, type="string") for name in sorted(input_param_names)]
    risky_count = sum(1 for tag in risk_tags if tag == RiskTag.RISKY)

    existing = store.latest_version(capability_id, tenant_scope="*")
    new_version_number = 1
    compatibility = Compatibility.BACKWARD
    if existing:
        new_version_number = existing["version"] + 1
        previous_artifact = CapabilityArtifact.model_validate_json(existing["artifact_json"])
        compatibility = classify_compatibility(
            previous_input_params=previous_artifact.input_params,
            previous_outputs=previous_artifact.outputs,
            previous_checkpoints=previous_artifact.checkpoints,
            new_input_params=input_params,
            new_outputs=outputs,
            new_checkpoints=checkpoints,
        )

    artifact = CapabilityArtifact(
        capability_id=capability_id,
        version=new_version_number,
        compatibility=compatibility,
        tenant_scope="*",
        input_params=input_params,
        steps=steps,
        checkpoints=checkpoints,
        outputs=outputs,
        success_condition=run_succeeded.get("success_condition", ""),
        provenance=Provenance(discovery_run_id=discovery_run_id),
        risk_summary=RiskSummary(
            highest_risk_tag=RiskTag.RISKY if risky_count else RiskTag.SAFE,
            risky_step_count=risky_count,
            requires_preapproval=risky_count > 0,
        ),
    )

    store.insert_version(
        capability_id=capability_id,
        version=new_version_number,
        tenant_scope="*",
        compatibility=compatibility.value,
        artifact_json=artifact.model_dump_json(),
        discovery_run_id=discovery_run_id,
    )

    return artifact
