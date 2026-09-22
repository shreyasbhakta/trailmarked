from __future__ import annotations

import json

import grpc

from shared.grpc_stubs import replay_pb2, replay_pb2_grpc

DEFAULT_ADDRESS = "localhost:50053"
_OUTCOME_FROM_PROTO = {0: "PENDING", 1: "BUSINESS_OUTCOME", 2: "RECOVERABLE", 3: "HARD_FAILURE"}


class ReplayRuntimeClient:
    def __init__(self, address: str = DEFAULT_ADDRESS):
        self._channel = grpc.insecure_channel(address)
        self._stub = replay_pb2_grpc.ReplayRuntimeStub(self._channel)

    def submit_replay(self, capability_id: str, tenant_id: str, idempotency_key: str, input_params: dict, correlation_id: str = "", version: int = 0) -> dict:
        response = self._stub.SubmitReplay(
            replay_pb2.ReplayRequest(
                capability_id=capability_id,
                version=version,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                input_params_json=json.dumps(input_params).encode("utf-8"),
                correlation_id=correlation_id,
            )
        )
        return {"run_id": response.run_id, "deduplicated": response.deduplicated}

    def get_circuit_breaker_state(self, target_key: str) -> dict:
        response = self._stub.GetCircuitBreakerState(replay_pb2.CircuitBreakerRequest(target_key=target_key))
        return {
            "state": ["CLOSED", "OPEN", "HALF_OPEN"][response.state],
            "consecutive_failures": response.consecutive_failures,
            "cooldown_until_epoch_ms": response.cooldown_until_epoch_ms,
        }

    def act_on_live_session(self, run_id: str, action_type: str, locator: str, value: str = "") -> None:
        self._stub.ActOnLiveSession(
            replay_pb2.ActOnLiveSessionRequest(run_id=run_id, action_type=action_type, locator=locator, value=value)
        )

    def release_live_session(self, run_id: str, terminate: bool = True) -> None:
        self._stub.ReleaseLiveSession(replay_pb2.ReleaseLiveSessionRequest(run_id=run_id, terminate=terminate))

    def get_status(self, run_id: str) -> dict:
        response = self._stub.GetReplayStatus(replay_pb2.ReplayStatusRequest(run_id=run_id))
        return {
            "run_id": response.run_id,
            "outcome": _OUTCOME_FROM_PROTO[response.outcome],
            "outputs": json.loads(response.outputs_json.decode("utf-8")) if response.outputs_json else {},
            "retry_count": response.retry_count,
            "failed_step_id": response.failed_step_id,
            "dead_letter_event_id": response.dead_letter_event_id,
        }
