"""Discovery-run orchestrator. Its real output is the event stream in the
event log, not a return value: every step emits a domain event via the
local outbox, so the run's history survives a crash mid-run and is fully
reconstructable from /evidence/ by correlation_id.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from services.discovery_plane.actor import execute as execute_action
from services.discovery_plane.planner import Planner
from shared import outbox
from shared.correlation import new_correlation_id
from shared.safety import AllowlistViolation, check_allowlist, classify_risk
from shared.schemas import DomainEventType, RiskTag, new_id

logger = logging.getLogger("discovery_plane")

DB_PATH = Path(__file__).parent / "discovery_plane.db"
TOPIC = "discovery.events"
MAX_STEPS = 15


class DiscoveryRun:
    def __init__(
        self,
        goal: str,
        capability_id: str,
        tenant_id: str,
        base_url: str,
        inputs: dict[str, str] | None = None,
        planner: Planner | None = None,
    ):
        self.goal = goal
        self.capability_id = capability_id
        self.tenant_id = tenant_id
        self.base_url = base_url
        self.inputs = inputs or {}
        self.run_id = new_id("run")
        self.correlation_id = new_correlation_id()
        self.planner = planner or Planner()

        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        outbox.ensure_outbox_schema(self._conn)
        self._dispatcher = outbox.OutboxDispatcher(DB_PATH)
        self._dispatcher.start()

    def _emit(self, event_type: DomainEventType, payload: dict) -> None:
        payload = {**payload, "run_id": self.run_id}
        with self._conn:
            outbox.enqueue(self._conn, TOPIC, self.correlation_id, event_type.value, payload)

    def _match_input_bindings(self, params: dict) -> dict[str, str]:
        """Marks which of this step's params carry one of the run's declared
        inputs, by literal-value match against the discovery-time argument.
        The registry compiler uses this to know which params to re-bind to
        the caller's arguments at replay time, instead of baking in the
        literal value seen during discovery.
        """
        bindings: dict[str, str] = {}
        for param_key, param_value in params.items():
            if not isinstance(param_value, str):
                continue
            for input_name, input_value in self.inputs.items():
                if input_value and input_value in param_value:
                    bindings[param_key] = input_name
        return bindings

    def execute(self) -> dict:
        history: list[dict] = []
        outputs: dict = {}
        final_status = "RunFailed"
        failure_reason = "max steps exceeded"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()

            # Step 0 is always the entry navigation, bound to the "entry_url"
            # input so a replay (or a different tenant's overlay) can target
            # a different starting URL without recompiling the capability.
            self._emit(
                DomainEventType.ACTION_DECIDED,
                {
                    "step_index": 0, "action_type": "navigate", "target_description": "open application entry point",
                    "locator_candidates": [], "params": {"url": self.base_url}, "risk_tag": RiskTag.SAFE.value,
                    "rationale": "start of run", "param_bindings": {"url": "entry_url"},
                },
            )
            page.goto(self.base_url)
            self._emit(DomainEventType.ACTION_EXECUTED, {"step_index": 0, "locator_used": None, "outcome": "success", "error_message": None})
            self._emit(DomainEventType.STEP_SUCCEEDED, {"step_index": 0, "checkpoint_assertions": []})

            for step_index in range(1, MAX_STEPS):
                snapshot = page.locator("body").aria_snapshot()
                self._emit(
                    DomainEventType.OBSERVATION_CAPTURED,
                    {"step_index": step_index, "a11y_snapshot": snapshot, "url": page.url},
                )

                action = self.planner.decide(self.goal, snapshot, page.url, history)
                risk_tag = classify_risk(action.action_type, action.target_description)
                param_bindings = self._match_input_bindings(action.params)
                self._emit(
                    DomainEventType.ACTION_DECIDED,
                    {
                        "step_index": step_index,
                        "action_type": action.action_type,
                        "target_description": action.target_description,
                        "locator_candidates": action.locator_candidates,
                        "params": action.params,
                        "risk_tag": risk_tag.value,
                        "rationale": action.rationale,
                        "param_bindings": param_bindings,
                    },
                )

                domain = urlparse(page.url).hostname or "localhost"
                gate_action_type = "assert" if action.action_type in ("assert", "extract", "finish") else action.action_type
                try:
                    check_allowlist(domain, gate_action_type)
                except AllowlistViolation as exc:
                    self._emit(
                        DomainEventType.ACTION_BLOCKED,
                        {"step_index": step_index, "reason": str(exc), "domain": domain, "action_type": action.action_type},
                    )
                    failure_reason = f"blocked by allowlist: {exc}"
                    break

                if action.action_type == "finish":
                    outputs = action.params.get("outputs", {})
                    if "error" in outputs:
                        failure_reason = outputs["error"]
                        break
                    final_status = "RunSucceeded"
                    self._emit(
                        DomainEventType.RUN_SUCCEEDED,
                        {
                            "capability_id": self.capability_id,
                            "tenant_id": self.tenant_id,
                            "goal": self.goal,
                            "outputs": outputs,
                            "success_condition": action.params.get("success_condition", ""),
                        },
                    )
                    break

                result = execute_action(page, action)
                self._emit(
                    DomainEventType.ACTION_EXECUTED,
                    {
                        "step_index": step_index,
                        "locator_used": result.locator_used,
                        "outcome": result.outcome,
                        "error_message": result.error_message,
                    },
                )

                if result.outcome == "error":
                    self._emit(DomainEventType.STEP_FAILED, {"step_index": step_index, "reason": result.error_message})
                    failure_reason = result.error_message or "step failed"
                    break

                if action.action_type == "extract" and result.extracted_value is not None:
                    output_name = action.params.get("output_name", f"step_{step_index}_output")
                    outputs[output_name] = result.extracted_value

                self._emit(DomainEventType.STEP_SUCCEEDED, {"step_index": step_index, "checkpoint_assertions": []})
                history.append(
                    {"action_type": action.action_type, "target_description": action.target_description, "outcome": result.outcome}
                )

            browser.close()

        if final_status != "RunSucceeded":
            self._emit(DomainEventType.RUN_FAILED, {"goal": self.goal, "reason": failure_reason})

        self._flush_and_stop()
        return {"run_id": self.run_id, "correlation_id": self.correlation_id, "status": final_status, "outputs": outputs}

    def _flush_and_stop(self) -> None:
        # Drain any outbox rows synchronously before the dispatcher thread stops,
        # so the caller can rely on every event already being in the log.
        self._dispatcher.dispatch_once(self._conn)
        self._dispatcher.stop()
