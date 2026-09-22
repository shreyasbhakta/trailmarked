from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Outcome(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PENDING: _ClassVar[Outcome]
    BUSINESS_OUTCOME: _ClassVar[Outcome]
    RECOVERABLE: _ClassVar[Outcome]
    HARD_FAILURE: _ClassVar[Outcome]
PENDING: Outcome
BUSINESS_OUTCOME: Outcome
RECOVERABLE: Outcome
HARD_FAILURE: Outcome

class Ack(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ActOnLiveSessionRequest(_message.Message):
    __slots__ = ("run_id", "action_type", "locator", "value")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_TYPE_FIELD_NUMBER: _ClassVar[int]
    LOCATOR_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    action_type: str
    locator: str
    value: str
    def __init__(self, run_id: _Optional[str] = ..., action_type: _Optional[str] = ..., locator: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class ReleaseLiveSessionRequest(_message.Message):
    __slots__ = ("run_id", "terminate")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    TERMINATE_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    terminate: bool
    def __init__(self, run_id: _Optional[str] = ..., terminate: _Optional[bool] = ...) -> None: ...

class ReplayRequest(_message.Message):
    __slots__ = ("capability_id", "version", "tenant_id", "idempotency_key", "input_params_json", "correlation_id")
    CAPABILITY_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    INPUT_PARAMS_JSON_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    capability_id: str
    version: int
    tenant_id: str
    idempotency_key: str
    input_params_json: bytes
    correlation_id: str
    def __init__(self, capability_id: _Optional[str] = ..., version: _Optional[int] = ..., tenant_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., input_params_json: _Optional[bytes] = ..., correlation_id: _Optional[str] = ...) -> None: ...

class ReplayAck(_message.Message):
    __slots__ = ("run_id", "deduplicated")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    DEDUPLICATED_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    deduplicated: bool
    def __init__(self, run_id: _Optional[str] = ..., deduplicated: _Optional[bool] = ...) -> None: ...

class ReplayStatusRequest(_message.Message):
    __slots__ = ("run_id",)
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    def __init__(self, run_id: _Optional[str] = ...) -> None: ...

class ReplayStatus(_message.Message):
    __slots__ = ("run_id", "outcome", "outputs_json", "retry_count", "failed_step_id", "dead_letter_event_id")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    OUTCOME_FIELD_NUMBER: _ClassVar[int]
    OUTPUTS_JSON_FIELD_NUMBER: _ClassVar[int]
    RETRY_COUNT_FIELD_NUMBER: _ClassVar[int]
    FAILED_STEP_ID_FIELD_NUMBER: _ClassVar[int]
    DEAD_LETTER_EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    outcome: Outcome
    outputs_json: bytes
    retry_count: int
    failed_step_id: str
    dead_letter_event_id: str
    def __init__(self, run_id: _Optional[str] = ..., outcome: _Optional[_Union[Outcome, str]] = ..., outputs_json: _Optional[bytes] = ..., retry_count: _Optional[int] = ..., failed_step_id: _Optional[str] = ..., dead_letter_event_id: _Optional[str] = ...) -> None: ...

class CircuitBreakerRequest(_message.Message):
    __slots__ = ("target_key",)
    TARGET_KEY_FIELD_NUMBER: _ClassVar[int]
    target_key: str
    def __init__(self, target_key: _Optional[str] = ...) -> None: ...

class CircuitBreakerState(_message.Message):
    __slots__ = ("state", "consecutive_failures", "cooldown_until_epoch_ms")
    class State(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        CLOSED: _ClassVar[CircuitBreakerState.State]
        OPEN: _ClassVar[CircuitBreakerState.State]
        HALF_OPEN: _ClassVar[CircuitBreakerState.State]
    CLOSED: CircuitBreakerState.State
    OPEN: CircuitBreakerState.State
    HALF_OPEN: CircuitBreakerState.State
    STATE_FIELD_NUMBER: _ClassVar[int]
    CONSECUTIVE_FAILURES_FIELD_NUMBER: _ClassVar[int]
    COOLDOWN_UNTIL_EPOCH_MS_FIELD_NUMBER: _ClassVar[int]
    state: CircuitBreakerState.State
    consecutive_failures: int
    cooldown_until_epoch_ms: int
    def __init__(self, state: _Optional[_Union[CircuitBreakerState.State, str]] = ..., consecutive_failures: _Optional[int] = ..., cooldown_until_epoch_ms: _Optional[int] = ...) -> None: ...
