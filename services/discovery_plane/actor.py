"""Executes a PlannedAction via Playwright, trying locator_candidates in order.
Whichever candidate resolves becomes locator_used; the full ordered list is
what the capability compiler later stores as a step's fallback locator chain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from services.discovery_plane.planner import PlannedAction

RESOLVE_TIMEOUT_MS = 3000


@dataclass
class ExecutionResult:
    outcome: str  # "success" | "error"
    locator_used: str | None = None
    error_message: str | None = None
    extracted_value: str | None = None
    assertion_passed: bool | None = None


def _resolve_locator(page: Page, candidates: list[str]):
    for candidate in candidates:
        try:
            locator = page.locator(candidate)
            if locator.count() >= 1:
                return candidate, locator.first
        except Exception:
            continue
    return None, None


def execute(page: Page, action: PlannedAction) -> ExecutionResult:
    try:
        if action.action_type == "navigate":
            page.goto(action.params["url"], timeout=RESOLVE_TIMEOUT_MS * 3)
            return ExecutionResult(outcome="success", locator_used=None)

        if action.action_type in ("click", "fill", "select", "extract"):
            candidate, locator = _resolve_locator(page, action.locator_candidates)
            if locator is None:
                return ExecutionResult(outcome="error", error_message="no locator candidate resolved")

            if action.action_type == "click":
                locator.click(timeout=RESOLVE_TIMEOUT_MS)
            elif action.action_type == "fill":
                locator.fill(str(action.params.get("value", "")), timeout=RESOLVE_TIMEOUT_MS)
            elif action.action_type == "select":
                locator.select_option(str(action.params.get("value", "")), timeout=RESOLVE_TIMEOUT_MS)
            elif action.action_type == "extract":
                value = locator.inner_text(timeout=RESOLVE_TIMEOUT_MS)
                return ExecutionResult(outcome="success", locator_used=candidate, extracted_value=value)

            return ExecutionResult(outcome="success", locator_used=candidate)

        if action.action_type == "assert":
            return _run_assertion(page, action.params)

        return ExecutionResult(outcome="error", error_message=f"unhandled action_type {action.action_type}")

    except PlaywrightTimeoutError as exc:
        return ExecutionResult(outcome="error", error_message=f"timeout: {exc}")
    except Exception as exc:  # noqa: BLE001 - surfaced as a StepFailed event, not swallowed
        return ExecutionResult(outcome="error", error_message=str(exc))


def _run_assertion(page: Page, params: dict[str, Any]) -> ExecutionResult:
    assertion = params.get("assertion")
    expected = str(params.get("expected", ""))

    if assertion == "url_contains":
        passed = expected in page.url
    elif assertion == "text_present":
        passed = page.get_by_text(expected).count() > 0
    elif assertion == "element_visible":
        try:
            passed = page.locator(expected).first.is_visible()
        except Exception:
            passed = False
    else:
        return ExecutionResult(outcome="error", error_message=f"unknown assertion type {assertion}")

    if passed:
        return ExecutionResult(outcome="success", assertion_passed=True)
    return ExecutionResult(outcome="error", assertion_passed=False, error_message=f"assertion failed: {assertion}={expected!r}")
