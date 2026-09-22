"""Safety layer: allowlist enforcement, risk tagging, and pre-persist redaction.

Shared library rather than a service, because the allowlist check has to sit
directly on the ActionDecided -> ActionExecuted path (in-process, before the
Playwright call happens) and the redaction hook has to run before ANY event
is written — never after the fact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from shared.schemas import RiskTag

# (domain, action_type) allowlist. Anything not listed here is blocked
# before ActionDecided can become ActionExecuted.
_ALLOWED_ACTIONS: set[tuple[str, str]] = {
    ("localhost", "click"),
    ("localhost", "fill"),
    ("localhost", "select"),
    ("localhost", "navigate"),
    ("localhost", "assert"),
    ("localhost", "extract"),
    ("127.0.0.1", "click"),
    ("127.0.0.1", "fill"),
    ("127.0.0.1", "select"),
    ("127.0.0.1", "navigate"),
    ("127.0.0.1", "assert"),
    ("127.0.0.1", "extract"),
}

# Action types that mutate bank state and therefore require pre-approval on
# the capability or a pause-for-confirmation during discovery.
_RISKY_ACTION_TYPES = {"click", "fill", "select"}
_RISKY_TARGET_KEYWORDS = ("submit", "confirm", "open sub-account", "transfer", "close")


class AllowlistViolation(Exception):
    def __init__(self, domain: str, action_type: str):
        super().__init__(f"blocked: ({domain}, {action_type}) not in allowlist")
        self.domain = domain
        self.action_type = action_type


def check_allowlist(domain: str, action_type: str) -> None:
    if (domain, action_type) not in _ALLOWED_ACTIONS:
        raise AllowlistViolation(domain, action_type)


def classify_risk(action_type: str, target_description: str) -> RiskTag:
    if action_type not in _RISKY_ACTION_TYPES:
        return RiskTag.SAFE
    lowered = target_description.lower()
    if any(keyword in lowered for keyword in _RISKY_TARGET_KEYWORDS):
        return RiskTag.RISKY
    return RiskTag.SAFE


_REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b\d{9,16}\b"), "[REDACTED_ACCOUNT_NUMBER]"),
    (re.compile(r"\b(?:sk|pk|token)_[A-Za-z0-9]{8,}\b", re.IGNORECASE), "[REDACTED_TOKEN]"),
    (re.compile(r"\bpassword\s*[:=]\s*\S+", re.IGNORECASE), "password=[REDACTED]"),
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_payload(payload: dict) -> dict:
    """Recursively redacts string values in a JSON-like dict before it is persisted."""
    redacted: dict = {}
    for key, value in payload.items():
        if isinstance(value, str):
            redacted[key] = redact(value)
        elif isinstance(value, dict):
            redacted[key] = redact_payload(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_payload(item) if isinstance(item, dict) else (redact(item) if isinstance(item, str) else item)
                for item in value
            ]
        else:
            redacted[key] = value
    return redacted


@dataclass
class RiskSummaryInput:
    risk_tags: list[RiskTag]

    def highest(self) -> RiskTag:
        return RiskTag.RISKY if RiskTag.RISKY in self.risk_tags else RiskTag.SAFE

    def risky_count(self) -> int:
        return sum(1 for tag in self.risk_tags if tag == RiskTag.RISKY)
