from __future__ import annotations

import json
import logging
from concurrent import futures
from pathlib import Path

import grpc
from playwright.sync_api import sync_playwright

from services.capability_registry.client import CapabilityRegistryClient
from services.escalation_saga.client import EscalationSagaClient
from services.event_log.client import EventLogClient
from services.replay_runtime import executor
from services.replay_runtime.circuit_breaker import CircuitBreaker, CircuitOpenError
from services.replay_runtime.store import DB_PATH as REPLAY_DB_PATH, ReplayStore
from shared import outbox
from shared.grpc_stubs import replay_pb2, replay_pb2_grpc
from shared.schemas import CapabilityArtifact, new_id

logger = logging.getLogger("replay_runtime")

DEFAULT_PORT = 50053
TOPIC = "replay.events"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"


class _PlaywrightSession:
    """Playwright's sync API binds its driver to whichever thread calls
    .start(), via a greenlet running in that thread. gRPC's own
    ThreadPoolExecutor can hand different calls to the same worker thread,
    which corrupts that state if two unrelated Playwright sessions ever
    touch the same thread. Each session gets its own dedicated single
    worker thread for its entire lifetime to rule that out — including for
    a hard-failed run kept alive for escalation, where later
    ActOnLiveSession/ReleaseLiveSession calls must run on that SAME thread.
    """

    def __init__(self):
        self._executor = futures.ThreadPoolExecutor(max_workers=1)
        self.playwright = None
        self.browser = None
        self.page = None
        self._executor.submit(self._launch).result()

    def _launch(self) -> None:
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.page = self.browser.new_page()

    def run(self, fn):
        return self._executor.submit(fn, self.page).result()

    def close(self) -> None:
        def _close(_page):
            self.browser.close()
            self.playwright.stop()

        self._executor.submit(_close, self.page).result()
        self._executor.shutdown(wait=False)

_OUTCOME_TO_PROTO = {
    "PENDING": replay_pb2.PENDING,
    "BUSINESS_OUTCOME": replay_pb2.BUSINESS_OUTCOME,
    "RECOVERABLE": replay_pb2.RECOVERABLE,
    "HARD_FAILURE": replay_pb2.HARD_FAILURE,
}
_STATE_TO_PROTO = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}


class ReplayRuntimeServicer(replay_pb2_grpc.ReplayRuntimeServicer):
    def __init__(self):
        self._store = ReplayStore()
        self._breaker = CircuitBreaker()
        self._registry = CapabilityRegistryClient()
        self._event_log = EventLogClient()
        self._escalation = EscalationSagaClient()
        outbox.ensure_outbox_schema(self._store.conn)
        self._dispatcher = outbox.OutboxDispatcher(REPLAY_DB_PATH)
        self._dispatcher.start()
        # Hard-failed runs keep their Playwright session here, alive and
        # un-closed, so the escalation saga can act on the SAME browser
        # rather than a fresh one. Resuming the deterministic loop after a
        # human hands control back is not implemented (see REPORT Cuts) —
        # ReleaseLiveSession always closes the session.
        self._live_sessions: dict[str, tuple] = {}

    def _emit(self, correlation_id: str, event_type: str, payload: dict) -> None:
        with self._store.conn:
            outbox.enqueue(self._store.conn, TOPIC, correlation_id, event_type, payload)

    def _capture_failure_screenshot(self, session: "_PlaywrightSession", run_id: str) -> str | None:
        """The structured expected/observed text tells you what broke; a
        screenshot of the actual page at the moment of HARD_FAILURE is the
        richer signal for a human debugging it after the fact.
        """
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / f"{run_id}.png"
        relative_path = "services/replay_runtime/screenshots/" + path.name
        try:
            session.run(lambda page: page.screenshot(path=str(path)))
            return relative_path
        except Exception:
            logger.exception("failed to capture failure screenshot for run %s", run_id)
            return None

    def SubmitReplay(self, request, context):
        cached = self._store.find_by_idempotency_key(request.idempotency_key) if request.idempotency_key else None
        if cached:
            return replay_pb2.ReplayAck(run_id=cached["run_id"], deduplicated=True)

        run_id = new_id("replay")
        correlation_id = request.correlation_id or new_id("corr")
        inputs = json.loads(request.input_params_json.decode("utf-8")) if request.input_params_json else {}
        version = request.version or 0

        self._store.create_pending(run_id, request.idempotency_key, request.capability_id, version, request.tenant_id, correlation_id)
        self._emit(correlation_id, "ReplayRequested", {
            "run_id": run_id, "capability_id": request.capability_id, "tenant_id": request.tenant_id, "input_params": inputs,
        })

        target_key = f"{request.tenant_id}:{request.capability_id}"
        try:
            self._breaker.before_run(target_key)
        except CircuitOpenError as exc:
            self._store.complete(run_id, "HARD_FAILURE", {}, 0, None, None)
            self._emit(correlation_id, "ReplayHardFailure", {
                "run_id": run_id, "reason": "circuit breaker open", "cooldown_until_ms": exc.cooldown_until_ms,
            })
            return replay_pb2.ReplayAck(run_id=run_id, deduplicated=False)

        artifact_dict = self._registry.resolve_for_tenant(request.capability_id, request.tenant_id, version)
        artifact = CapabilityArtifact.model_validate(artifact_dict)

        session = _PlaywrightSession()
        result = session.run(lambda page: executor.run(page, artifact, inputs))

        screenshot_path = None
        if result.outcome == "HARD_FAILURE":
            screenshot_path = self._capture_failure_screenshot(session, run_id)
            self._live_sessions[run_id] = session
        else:
            session.close()

        for step in result.step_log:
            self._emit(correlation_id, "ReplayStepExecuted", {
                "run_id": run_id, "step_id": step.step_id, "outcome": step.outcome, "detail": step.detail,
            })

        dead_letter_event_id = None
        if result.outcome == "HARD_FAILURE":
            self._breaker.record_failure(target_key)
            failure_context = {**(result.dead_letter_context or {}), "screenshot_path": screenshot_path}
            dead_letter_event_id = self._event_log.dead_letter(
                source_topic=TOPIC,
                correlation_id=correlation_id,
                failure_reason=f"hard failure at step {result.failed_step_id}",
                original_payload={"run_id": run_id, "capability_id": request.capability_id, "step": result.failed_step_id},
                failure_context=failure_context,
            )
            self._emit(correlation_id, "ReplayHardFailure", {
                "run_id": run_id, "failed_step_id": result.failed_step_id, "dead_letter_event_id": dead_letter_event_id,
                "context": failure_context,
            })
            self._escalation.request_intervention(
                run_id=run_id, correlation_id=correlation_id, dead_letter_event_id=dead_letter_event_id,
                failed_step_id=result.failed_step_id or "", reason=f"hard failure at step {result.failed_step_id}",
                context=failure_context,
            )
        elif result.outcome == "BUSINESS_OUTCOME":
            self._breaker.record_success(target_key)
            self._emit(correlation_id, "ReplaySucceeded", {"run_id": run_id, "outputs": result.outputs, "retry_count": result.retry_count})
        else:
            self._breaker.record_failure(target_key)

        self._dispatcher.dispatch_once(self._store.conn)
        self._store.complete(run_id, result.outcome, result.outputs, result.retry_count, result.failed_step_id, dead_letter_event_id)
        return replay_pb2.ReplayAck(run_id=run_id, deduplicated=False)

    def GetReplayStatus(self, request, context):
        row = self._store.get(request.run_id)
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, f"replay run {request.run_id} not found")
        return replay_pb2.ReplayStatus(
            run_id=row["run_id"],
            outcome=_OUTCOME_TO_PROTO.get(row["outcome"], replay_pb2.PENDING),
            outputs_json=json.dumps(row["outputs"]).encode("utf-8"),
            retry_count=row["retry_count"],
            failed_step_id=row["failed_step_id"] or "",
            dead_letter_event_id=row["dead_letter_event_id"] or "",
        )

    def ActOnLiveSession(self, request, context):
        session = self._live_sessions.get(request.run_id)
        if session is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"no live session for run {request.run_id}")

        def _act(page):
            locator = page.locator(request.locator).first
            if request.action_type == "click":
                locator.click(timeout=5000)
            elif request.action_type == "fill":
                locator.fill(request.value, timeout=5000)
            elif request.action_type == "select":
                locator.select_option(request.value, timeout=5000)
            else:
                raise ValueError(f"unsupported action_type {request.action_type}")

        session.run(_act)
        return replay_pb2.Ack()

    def ReleaseLiveSession(self, request, context):
        session = self._live_sessions.pop(request.run_id, None)
        if session is not None:
            session.close()
        return replay_pb2.Ack()

    def GetCircuitBreakerState(self, request, context):
        state = self._breaker.state(request.target_key)
        return replay_pb2.CircuitBreakerState(
            state=_STATE_TO_PROTO[state["state"]],
            consecutive_failures=state["consecutive_failures"],
            cooldown_until_epoch_ms=state["cooldown_until_ms"],
        )


def serve(port: int = DEFAULT_PORT) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    replay_pb2_grpc.add_ReplayRuntimeServicer_to_server(ReplayRuntimeServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("replay_runtime gRPC listening on :%d", port)
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    server = serve()
    server.wait_for_termination()
