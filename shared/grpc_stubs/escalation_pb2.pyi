from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SagaStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AGENT_CONTROLLED: _ClassVar[SagaStatus]
    INTERVENTION_REQUESTED: _ClassVar[SagaStatus]
    HUMAN_CONTROLLED: _ClassVar[SagaStatus]
    CONTROL_RETURNED: _ClassVar[SagaStatus]
    RESUMED: _ClassVar[SagaStatus]
    TERMINATED: _ClassVar[SagaStatus]
AGENT_CONTROLLED: SagaStatus
INTERVENTION_REQUESTED: SagaStatus
HUMAN_CONTROLLED: SagaStatus
CONTROL_RETURNED: SagaStatus
RESUMED: SagaStatus
TERMINATED: SagaStatus

class ListSagasRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListSagasResponse(_message.Message):
    __slots__ = ("sagas",)
    SAGAS_FIELD_NUMBER: _ClassVar[int]
    sagas: _containers.RepeatedCompositeFieldContainer[SagaState]
    def __init__(self, sagas: _Optional[_Iterable[_Union[SagaState, _Mapping]]] = ...) -> None: ...

class InterventionRequest(_message.Message):
    __slots__ = ("run_id", "correlation_id", "dead_letter_event_id", "failed_step_id", "reason", "context_json")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    DEAD_LETTER_EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    FAILED_STEP_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_JSON_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    correlation_id: str
    dead_letter_event_id: str
    failed_step_id: str
    reason: str
    context_json: bytes
    def __init__(self, run_id: _Optional[str] = ..., correlation_id: _Optional[str] = ..., dead_letter_event_id: _Optional[str] = ..., failed_step_id: _Optional[str] = ..., reason: _Optional[str] = ..., context_json: _Optional[bytes] = ...) -> None: ...

class InterventionAck(_message.Message):
    __slots__ = ("saga_id", "status")
    SAGA_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    saga_id: str
    status: SagaStatus
    def __init__(self, saga_id: _Optional[str] = ..., status: _Optional[_Union[SagaStatus, str]] = ...) -> None: ...

class ClaimRequest(_message.Message):
    __slots__ = ("saga_id", "operator_id")
    SAGA_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_ID_FIELD_NUMBER: _ClassVar[int]
    saga_id: str
    operator_id: str
    def __init__(self, saga_id: _Optional[str] = ..., operator_id: _Optional[str] = ...) -> None: ...

class ClaimAck(_message.Message):
    __slots__ = ("saga_id", "session_handle", "status")
    SAGA_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_HANDLE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    saga_id: str
    session_handle: str
    status: SagaStatus
    def __init__(self, saga_id: _Optional[str] = ..., session_handle: _Optional[str] = ..., status: _Optional[_Union[SagaStatus, str]] = ...) -> None: ...

class HumanActionRequest(_message.Message):
    __slots__ = ("saga_id", "operator_id", "action_json")
    SAGA_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_JSON_FIELD_NUMBER: _ClassVar[int]
    saga_id: str
    operator_id: str
    action_json: bytes
    def __init__(self, saga_id: _Optional[str] = ..., operator_id: _Optional[str] = ..., action_json: _Optional[bytes] = ...) -> None: ...

class Ack(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ReleaseRequest(_message.Message):
    __slots__ = ("saga_id", "operator_id", "resume_agent")
    SAGA_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_ID_FIELD_NUMBER: _ClassVar[int]
    RESUME_AGENT_FIELD_NUMBER: _ClassVar[int]
    saga_id: str
    operator_id: str
    resume_agent: bool
    def __init__(self, saga_id: _Optional[str] = ..., operator_id: _Optional[str] = ..., resume_agent: _Optional[bool] = ...) -> None: ...

class ReleaseAck(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: SagaStatus
    def __init__(self, status: _Optional[_Union[SagaStatus, str]] = ...) -> None: ...

class SagaStateRequest(_message.Message):
    __slots__ = ("saga_id",)
    SAGA_ID_FIELD_NUMBER: _ClassVar[int]
    saga_id: str
    def __init__(self, saga_id: _Optional[str] = ...) -> None: ...

class SagaState(_message.Message):
    __slots__ = ("saga_id", "run_id", "status", "claimed_by_operator_id")
    SAGA_ID_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CLAIMED_BY_OPERATOR_ID_FIELD_NUMBER: _ClassVar[int]
    saga_id: str
    run_id: str
    status: SagaStatus
    claimed_by_operator_id: str
    def __init__(self, saga_id: _Optional[str] = ..., run_id: _Optional[str] = ..., status: _Optional[_Union[SagaStatus, str]] = ..., claimed_by_operator_id: _Optional[str] = ...) -> None: ...
