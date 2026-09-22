"""Deterministic execution of a resolved CapabilityArtifact. No LLM call
happens anywhere in this module — that is the one rule the replay runtime
never breaks. Locator resolution falls back through a step's strategy
chain; checkpoints are asserted, never assumed.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from shared.schemas import CapabilityArtifact, CapabilityStep, Checkpoint

MAX_RETRIES_PER_STEP = 2
BASE_BACKOFF_S = 0.5

_BUSINESS_OUTCOME_MARKERS = ("Member Not Found", "Permission Denied")


class RecoverableError(Exception):
    pass


class HardFailureError(Exception):
    def __init__(self, message: str, expected: str, observed: str):
        super().__init__(message)
        self.expected = expected
        self.observed = observed


class BusinessOutcomeSignal(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class StepExecution:
    step_id: str
    outcome: str  # success | recoverable_retry | business_outcome | hard_failure
    locator_used: str | None = None
    detail: str = ""


@dataclass
class ReplayResult:
    outcome: str  # BUSINESS_OUTCOME | RECOVERABLE | HARD_FAILURE
    outputs: dict = field(default_factory=dict)
    retry_count: int = 0
    failed_step_id: str | None = None
    dead_letter_context: dict | None = None
    step_log: list[StepExecution] = field(default_factory=list)


def _resolve_param(step: CapabilityStep, key: str, inputs: dict) -> str:
    input_name = step.param_bindings.get(key)
    if input_name is None or input_name not in inputs:
        raise HardFailureError(
            f"step {step.step_id} has no input bound for param '{key}'",
            expected=f"input_params contains '{input_name}'",
            observed=f"inputs={list(inputs.keys())}",
        )
    return str(inputs[input_name])


def _resolve_locator(page: Page, step: CapabilityStep):
    for strategy in step.strategy_chain:
        candidate = f"{strategy.kind}={strategy.value}" if strategy.kind != "css" else f"css={strategy.value}"
        try:
            locator = page.locator(candidate)
            if locator.count() >= 1:
                return candidate, locator.first
        except Exception:
            continue
    return None, None


def _page_state_summary(page: Page) -> str:
    try:
        return f"url={page.url} title={page.title()}"
    except Exception:
        return "page state unavailable"


def _matches_business_outcome(page: Page) -> str | None:
    try:
        body_text = page.locator("body").inner_text(timeout=1000)
    except Exception:
        return None
    for marker in _BUSINESS_OUTCOME_MARKERS:
        if marker in body_text:
            return marker
    return None


def _execute_step(page: Page, step: CapabilityStep, inputs: dict, checkpoints_by_step: dict[str, Checkpoint], outputs: dict, output_name_by_step: dict[str, str]) -> str:
    if step.action_type == "navigate":
        url = _resolve_param(step, "url", inputs)
        try:
            page.goto(url, timeout=10_000)
        except PlaywrightTimeoutError as exc:
            raise RecoverableError(f"navigate timeout: {exc}") from exc
        except Exception as exc:
            # Connection refused / DNS failure / etc. — not a Playwright
            # timeout, but just as transient from the caller's perspective
            # (a stale entry_url, a target host that's briefly down).
            raise RecoverableError(f"navigate failed: {exc}") from exc
        return step.step_id

    if step.action_type in ("click", "fill", "select", "extract"):
        candidate, locator = _resolve_locator(page, step)
        if locator is None:
            business_marker = _matches_business_outcome(page)
            if business_marker:
                raise BusinessOutcomeSignal(business_marker)
            raise RecoverableError(f"no locator resolved for step {step.step_id}")

        try:
            if step.action_type == "click":
                locator.click(timeout=5000)
            elif step.action_type == "fill":
                locator.fill(_resolve_param(step, "value", inputs), timeout=5000)
            elif step.action_type == "select":
                locator.select_option(_resolve_param(step, "value", inputs), timeout=5000)
            elif step.action_type == "extract":
                output_name = output_name_by_step.get(step.step_id, step.step_id)
                outputs[output_name] = locator.inner_text(timeout=5000)
        except PlaywrightTimeoutError as exc:
            raise RecoverableError(f"action timeout on step {step.step_id}: {exc}") from exc
        except Exception as exc:
            raise RecoverableError(f"action failed on step {step.step_id}: {exc}") from exc
        return step.step_id

    if step.action_type == "assert":
        checkpoint = checkpoints_by_step.get(step.step_id)
        if checkpoint is None:
            raise HardFailureError(f"no checkpoint registered for step {step.step_id}", expected="checkpoint", observed="none")

        passed = _run_assertion(page, checkpoint)
        if passed:
            return step.step_id

        business_marker = _matches_business_outcome(page)
        if business_marker:
            raise BusinessOutcomeSignal(business_marker)

        raise HardFailureError(
            f"checkpoint failed at step {step.step_id}",
            expected=f"{checkpoint.assertion}={checkpoint.expected}",
            observed=_page_state_summary(page),
        )

    raise HardFailureError(f"unsupported action_type {step.action_type}", expected="known action_type", observed=step.action_type)


def _run_assertion(page: Page, checkpoint: Checkpoint) -> bool:
    if checkpoint.assertion == "url_contains":
        return checkpoint.expected in page.url
    if checkpoint.assertion == "text_present":
        return page.get_by_text(checkpoint.expected).count() > 0
    if checkpoint.assertion == "element_visible":
        try:
            return page.locator(checkpoint.expected).first.is_visible()
        except Exception:
            return False
    return False


def run(page: Page, artifact: CapabilityArtifact, inputs: dict) -> ReplayResult:
    checkpoints_by_step = {c.step_id: c for c in artifact.checkpoints}
    output_name_by_step = {o.extraction_source: o.name for o in artifact.outputs}
    outputs: dict = {}
    step_log: list[StepExecution] = []
    total_retries = 0

    for step in artifact.steps:
        attempt = 0
        while True:
            try:
                _execute_step(page, step, inputs, checkpoints_by_step, outputs, output_name_by_step)
                step_log.append(StepExecution(step.step_id, "success"))
                break
            except RecoverableError as exc:
                attempt += 1
                total_retries += 1
                if attempt > MAX_RETRIES_PER_STEP:
                    step_log.append(StepExecution(step.step_id, "hard_failure", detail=str(exc)))
                    return ReplayResult(
                        outcome="HARD_FAILURE",
                        outputs=outputs,
                        retry_count=total_retries,
                        failed_step_id=step.step_id,
                        dead_letter_context={"expected": "locator resolved and action succeeded", "observed": str(exc)},
                        step_log=step_log,
                    )
                step_log.append(StepExecution(step.step_id, "recoverable_retry", detail=str(exc)))
                time.sleep(BASE_BACKOFF_S * (2 ** (attempt - 1)) + random.uniform(0, 0.25))
                continue
            except BusinessOutcomeSignal as exc:
                step_log.append(StepExecution(step.step_id, "business_outcome", detail=exc.message))
                outputs["business_outcome"] = exc.message
                return ReplayResult(outcome="BUSINESS_OUTCOME", outputs=outputs, retry_count=total_retries, step_log=step_log)
            except HardFailureError as exc:
                step_log.append(StepExecution(step.step_id, "hard_failure", detail=str(exc)))
                return ReplayResult(
                    outcome="HARD_FAILURE",
                    outputs=outputs,
                    retry_count=total_retries,
                    failed_step_id=step.step_id,
                    dead_letter_context={"expected": exc.expected, "observed": exc.observed},
                    step_log=step_log,
                )
            except Exception as exc:  # noqa: BLE001 - an unclassified failure still dead-letters, never crashes the run
                step_log.append(StepExecution(step.step_id, "hard_failure", detail=str(exc)))
                return ReplayResult(
                    outcome="HARD_FAILURE",
                    outputs=outputs,
                    retry_count=total_retries,
                    failed_step_id=step.step_id,
                    dead_letter_context={"expected": "no unhandled exception", "observed": str(exc)},
                    step_log=step_log,
                )

    return ReplayResult(outcome="BUSINESS_OUTCOME", outputs=outputs, retry_count=total_retries, step_log=step_log)
