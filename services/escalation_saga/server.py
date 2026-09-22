from __future__ import annotations

import json
import logging
from concurrent import futures

import grpc

from services.replay_runtime.client import ReplayRuntimeClient
from services.escalation_saga.store import DB_PATH as SAGA_DB_PATH, SagaStore
from shared import outbox
from shared.grpc_stubs import escalation_pb2, escalation_pb2_grpc
from shared.schemas import new_id

logger = logging.getLogger("escalation_saga")

DEFAULT_PORT = 50054
TOPIC = "escalation.events"

_STATUS_TO_PROTO = {
    "AGENT_CONTROLLED": escalation_pb2.AGENT_CONTROLLED,
    "INTERVENTION_REQUESTED": escalation_pb2.INTERVENTION_REQUESTED,
    "HUMAN_CONTROLLED": escalation_pb2.HUMAN_CONTROLLED,
    "CONTROL_RETURNED": escalation_pb2.CONTROL_RETURNED,
    "RESUMED": escalation_pb2.RESUMED,
    "TERMINATED": escalation_pb2.TERMINATED,
}


class EscalationSagaServicer(escalation_pb2_grpc.EscalationSagaServicer):
    def __init__(self):
        self._store = SagaStore()
        self._replay_runtime = ReplayRuntimeClient()
        outbox.ensure_outbox_schema(self._store.conn)
        self._dispatcher = outbox.OutboxDispatcher(SAGA_DB_PATH)
        self._dispatcher.start()

    def _emit(self, correlation_id: str, event_type: str, payload: dict) -> None:
        with self._store.conn:
            outbox.enqueue(self._store.conn, TOPIC, correlation_id, event_type, payload)
        self._dispatcher.dispatch_once(self._store.conn)

    def RequestIntervention(self, request, context):
        saga_id = new_id("saga")
        context_dict = json.loads(request.context_json.decode("utf-8")) if request.context_json else {}
        self._store.create(saga_id, request.run_id, request.correlation_id, request.dead_letter_event_id, context_dict)
        self._emit(request.correlation_id, "InterventionRequested", {
            "saga_id": saga_id, "run_id": request.run_id, "dead_letter_event_id": request.dead_letter_event_id,
            "failed_step_id": request.failed_step_id, "reason": request.reason, "context": context_dict,
        })
        logger.warning("intervention requested saga_id=%s run_id=%s reason=%s", saga_id, request.run_id, request.reason)
        return escalation_pb2.InterventionAck(saga_id=saga_id, status=escalation_pb2.INTERVENTION_REQUESTED)

    def ClaimSession(self, request, context):
        saga = self._store.get(request.saga_id)
        if saga is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"saga {request.saga_id} not found")
        session_handle = f"live-session:{saga['run_id']}"
        self._store.claim(request.saga_id, request.operator_id, session_handle)
        self._emit(saga["correlation_id"], "ControlClaimed", {"saga_id": request.saga_id, "run_id": saga["run_id"], "operator_id": request.operator_id})
        return escalation_pb2.ClaimAck(saga_id=request.saga_id, session_handle=session_handle, status=escalation_pb2.HUMAN_CONTROLLED)

    def RecordHumanAction(self, request, context):
        saga = self._store.get(request.saga_id)
        if saga is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"saga {request.saga_id} not found")
        action = json.loads(request.action_json.decode("utf-8"))
        self._store.record_human_action(request.saga_id, request.operator_id, action)
        self._replay_runtime.act_on_live_session(
            run_id=saga["run_id"], action_type=action["action_type"], locator=action["locator"], value=action.get("value", "")
        )
        self._emit(saga["correlation_id"], "HumanActed", {"saga_id": request.saga_id, "run_id": saga["run_id"], "operator_id": request.operator_id, "action": action})
        return escalation_pb2.Ack()

    def ReleaseControl(self, request, context):
        saga = self._store.get(request.saga_id)
        if saga is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"saga {request.saga_id} not found")
        self._replay_runtime.release_live_session(saga["run_id"], terminate=True)
        status = "RESUMED" if request.resume_agent else "TERMINATED"
        self._store.release(request.saga_id, status)
        self._emit(saga["correlation_id"], "ControlReturned", {
            "saga_id": request.saga_id, "run_id": saga["run_id"], "operator_id": request.operator_id, "resume_agent": request.resume_agent,
        })
        return escalation_pb2.ReleaseAck(status=_STATUS_TO_PROTO[status])

    def GetSagaState(self, request, context):
        saga = self._store.get(request.saga_id)
        if saga is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"saga {request.saga_id} not found")
        return escalation_pb2.SagaState(
            saga_id=saga["saga_id"], run_id=saga["run_id"], status=_STATUS_TO_PROTO[saga["status"]],
            claimed_by_operator_id=saga["claimed_by_operator_id"] or "",
        )

    def ListSagas(self, request, context):
        return escalation_pb2.ListSagasResponse(
            sagas=[
                escalation_pb2.SagaState(
                    saga_id=s["saga_id"], run_id=s["run_id"], status=_STATUS_TO_PROTO[s["status"]],
                    claimed_by_operator_id=s["claimed_by_operator_id"] or "",
                )
                for s in self._store.list_all()
            ]
        )


def serve(port: int = DEFAULT_PORT) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    escalation_pb2_grpc.add_EscalationSagaServicer_to_server(EscalationSagaServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("escalation_saga gRPC listening on :%d", port)
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    server = serve()
    server.wait_for_termination()
