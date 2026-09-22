"""Correlation-id helpers threaded through every event, log line, and API call."""
import contextvars
import uuid

_current: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return f"corr_{uuid.uuid4().hex}"


def set_current(correlation_id: str) -> None:
    _current.set(correlation_id)


def get_current() -> str:
    value = _current.get()
    if value is None:
        value = new_correlation_id()
        _current.set(value)
    return value
