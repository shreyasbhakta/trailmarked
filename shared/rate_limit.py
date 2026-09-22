"""Per-(capability, tenant) rate limiting for the agent-facing invocation
API. An agent that misfires (a bad loop, a bug in its own planning) should
not be able to hammer a production banking UI at will — this is the
platform's own backstop, independent of whatever rate limiting the bank's
infrastructure might apply.
"""
from __future__ import annotations

import threading
import time
from collections import deque

WINDOW_S = 60.0
MAX_REQUESTS_PER_WINDOW = 20


class RateLimitExceeded(Exception):
    def __init__(self, key: str, retry_after_s: float):
        super().__init__(f"rate limit exceeded for {key}, retry after {retry_after_s:.1f}s")
        self.key = key
        self.retry_after_s = retry_after_s


class RateLimiter:
    def __init__(self, window_s: float = WINDOW_S, max_requests: int = MAX_REQUESTS_PER_WINDOW):
        self._window_s = window_s
        self._max_requests = max_requests
        self._lock = threading.Lock()
        self._hits: dict[str, deque] = {}

    def check(self, capability_id: str, tenant_id: str) -> None:
        key = f"{tenant_id}:{capability_id}"
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self._window_s:
                hits.popleft()
            if len(hits) >= self._max_requests:
                retry_after = self._window_s - (now - hits[0])
                raise RateLimitExceeded(key, retry_after)
            hits.append(now)
