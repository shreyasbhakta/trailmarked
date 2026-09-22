from __future__ import annotations

import json

import grpc

from shared.grpc_stubs import escalation_pb2, escalation_pb2_grpc

DEFAULT_ADDRESS = "localhost:50054"
_STATUS_FROM_PROTO = {
    0: "AGENT_CONTROLLED", 1: "INTERVENTION_REQUESTED", 2: "HUMAN_CONTROLLED",
    3: "CONTROL_RETURNED", 4: "RESUMED", 5: "TERMINATED",
}


class EscalationSagaClient:
    def __init__(self, address: str = DEFAULT_ADDRESS):
        self._channel = grpc.insecure_channel(address)
        self._stub = escalation_pb2_grpc.EscalationSagaStub(self._channel)

    def request_intervention(self, run_id: str, correlation_id: str, dead_letter_event_id: str, failed_step_id: str, reason: str, context: dict) -> dict:
        response = self._stub.RequestIntervention(
            escalation_pb2.InterventionRequest(
                run_id=run_id, correlation_id=correlation_id, dead_letter_event_id=dead_letter_event_id,
                failed_step_id=failed_step_id, reason=reason, context_json=json.dumps(context).encode("utf-8"),
            )
        )
        return {"saga_id": response.saga_id, "status": _STATUS_FROM_PROTO[response.status]}

    def claim_session(self, saga_id: str, operator_id: str) -> dict:
        response = self._stub.ClaimSession(escalation_pb2.ClaimRequest(saga_id=saga_id, operator_id=operator_id))
        return {"saga_id": response.saga_id, "session_handle": response.session_handle, "status": _STATUS_FROM_PROTO[response.status]}

    def record_human_action(self, saga_id: str, operator_id: str, action: dict) -> None:
        self._stub.RecordHumanAction(
            escalation_pb2.HumanActionRequest(saga_id=saga_id, operator_id=operator_id, action_json=json.dumps(action).encode("utf-8"))
        )

    def release_control(self, saga_id: str, operator_id: str, resume_agent: bool) -> dict:
        response = self._stub.ReleaseControl(
            escalation_pb2.ReleaseRequest(saga_id=saga_id, operator_id=operator_id, resume_agent=resume_agent)
        )
        return {"status": _STATUS_FROM_PROTO[response.status]}

    def get_saga_state(self, saga_id: str) -> dict:
        response = self._stub.GetSagaState(escalation_pb2.SagaStateRequest(saga_id=saga_id))
        return {
            "saga_id": response.saga_id, "run_id": response.run_id, "status": _STATUS_FROM_PROTO[response.status],
            "claimed_by_operator_id": response.claimed_by_operator_id,
        }

    def list_sagas(self) -> list[dict]:
        response = self._stub.ListSagas(escalation_pb2.ListSagasRequest())
        return [
            {"saga_id": s.saga_id, "run_id": s.run_id, "status": _STATUS_FROM_PROTO[s.status], "claimed_by_operator_id": s.claimed_by_operator_id}
            for s in response.sagas
        ]
