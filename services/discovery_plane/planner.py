"""LLM tool-calling planner: goal + a11y snapshot + action history in, one
structured action out per turn. This module is the only place in the whole
platform that calls an LLM — everything downstream of a trailmarked
capability runs deterministically without it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

import anthropic

MODEL = "claude-sonnet-5"

_ACTION_TOOL = {
    "name": "emit_action",
    "description": (
        "Decide the single next UI action to take toward the goal, given the current "
        "accessibility-tree snapshot and the history of actions already taken. Call this "
        "exactly once per turn."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action_type": {
                "type": "string",
                "enum": ["click", "fill", "select", "navigate", "assert", "extract", "finish"],
            },
            "target_description": {
                "type": "string",
                "description": "Human-readable description of the element or goal state being targeted.",
            },
            "locator_candidates": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Ordered Playwright locator strings to try (primary first, then fallbacks), e.g. "
                    "'role=button[name=\"Search\"]', 'label=Member ID:', 'text=Open Sub-Account', "
                    "'css=#acct-balance'. Empty for navigate/finish."
                ),
            },
            "params": {
                "type": "object",
                "description": (
                    "Action parameters. fill/select: {\"value\": ...}. navigate: {\"url\": ...}. "
                    "assert: {\"assertion\": \"text_present\"|\"url_contains\"|\"element_visible\", \"expected\": ...}. "
                    "extract: {\"output_name\": ...}. finish: {\"outputs\": {...}, \"success_condition\": ...}."
                ),
            },
            "rationale": {"type": "string"},
        },
        "required": ["action_type", "target_description", "locator_candidates", "params", "rationale"],
    },
}

SYSTEM_PROMPT = """You are the planning component of Trailmarked, a computer-use agent that learns \
UI tasks once so they can be replayed deterministically afterward without an LLM. You control a \
browser via a sequence of structured actions against a legacy, server-rendered internal banking \
tool. You perceive the page only through an accessibility-tree snapshot, never a screenshot.

Rules:
- Call emit_action exactly once per turn with the single next action.
- Prefer role= and label= locators over css= when the accessibility tree gives you a name/role.
  Never invent a css= id or class that isn't visible in the snapshot — the accessibility tree does
  not expose DOM ids or classes, so a guessed css= selector will not resolve.
- For text= locators, use the innermost leaf node's exact text as shown in the snapshot tree, not
  a concatenated parent/row label — a parent's accessible name can combine several child nodes'
  text in a way that does not match any single element's actual text content.
- Use action_type "assert" to verify an expected page state (e.g. after a form submission).
  Required: before any "extract" step, include at least one "assert" step confirming you have
  actually reached the expected page (e.g. assert.text_present on a heading/label that only
  appears on that page, or assert.url_contains on a distinctive path segment). Do not assume a
  click or navigation landed where you intended — check it. A replay of this capability will only
  ever verify what you assert here; if you never assert anything, nothing is ever checked.
- Use action_type "extract" to read a value off the page into the run's outputs (output_name).
- When the goal has been fully achieved, call emit_action with action_type "finish", empty \
locator_candidates, and params.outputs containing every value the goal asked you to capture, plus \
params.success_condition describing how success is recognized.
- If the page shows an error state (not found, permission denied, timeout) that prevents the goal \
from being reached, call emit_action with action_type "finish" and params.outputs = {"error": \
"<what went wrong>"}.
"""


@dataclass
class PlannedAction:
    action_type: Literal["click", "fill", "select", "navigate", "assert", "extract", "finish"]
    target_description: str
    locator_candidates: list[str]
    params: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


class Planner:
    def __init__(self, api_key: str | None = None):
        self._client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])

    def decide(
        self,
        goal: str,
        a11y_snapshot: str,
        current_url: str,
        history: list[dict[str, Any]],
    ) -> PlannedAction:
        history_text = "\n".join(
            f"{i + 1}. {h['action_type']} on \"{h['target_description']}\" -> {h['outcome']}"
            for i, h in enumerate(history)
        ) or "(no actions taken yet)"

        user_message = (
            f"GOAL: {goal}\n\n"
            f"CURRENT URL: {current_url}\n\n"
            f"ACCESSIBILITY SNAPSHOT:\n{a11y_snapshot}\n\n"
            f"ACTION HISTORY:\n{history_text}\n\n"
            "Call emit_action with the next single action."
        )

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[_ACTION_TOOL],
            tool_choice={"type": "tool", "name": "emit_action"},
            messages=[{"role": "user", "content": user_message}],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "emit_action":
                data = block.input
                return PlannedAction(
                    action_type=data["action_type"],
                    target_description=data["target_description"],
                    locator_candidates=data.get("locator_candidates", []),
                    params=data.get("params", {}),
                    rationale=data.get("rationale", ""),
                )

        raise RuntimeError("planner did not return an emit_action tool call")
