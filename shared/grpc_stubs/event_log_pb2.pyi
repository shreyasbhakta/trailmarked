import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Event(_message.Message):
    __slots__ = ("event_id", "topic", "offset", "correlation_id", "event_type", "occurred_at", "payload_json")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    topic: str
    offset: int
    correlation_id: str
    event_type: str
    occurred_at: _timestamp_pb2.Timestamp
    payload_json: bytes
    def __init__(self, event_id: _Optional[str] = ..., topic: _Optional[str] = ..., offset: _Optional[int] = ..., correlation_id: _Optional[str] = ..., event_type: _Optional[str] = ..., occurred_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., payload_json: _Optional[bytes] = ...) -> None: ...

class AppendRequest(_message.Message):
    __slots__ = ("topic", "correlation_id", "event_type", "payload_json", "producer_dedupe_key")
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    PRODUCER_DEDUPE_KEY_FIELD_NUMBER: _ClassVar[int]
    topic: str
    correlation_id: str
    event_type: str
    payload_json: bytes
    producer_dedupe_key: str
    def __init__(self, topic: _Optional[str] = ..., correlation_id: _Optional[str] = ..., event_type: _Optional[str] = ..., payload_json: _Optional[bytes] = ..., producer_dedupe_key: _Optional[str] = ...) -> None: ...

class AppendResponse(_message.Message):
    __slots__ = ("event_id", "offset")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    offset: int
    def __init__(self, event_id: _Optional[str] = ..., offset: _Optional[int] = ...) -> None: ...

class FetchRequest(_message.Message):
    __slots__ = ("topic", "consumer_group", "max_events")
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    CONSUMER_GROUP_FIELD_NUMBER: _ClassVar[int]
    MAX_EVENTS_FIELD_NUMBER: _ClassVar[int]
    topic: str
    consumer_group: str
    max_events: int
    def __init__(self, topic: _Optional[str] = ..., consumer_group: _Optional[str] = ..., max_events: _Optional[int] = ...) -> None: ...

class FetchResponse(_message.Message):
    __slots__ = ("events",)
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    events: _containers.RepeatedCompositeFieldContainer[Event]
    def __init__(self, events: _Optional[_Iterable[_Union[Event, _Mapping]]] = ...) -> None: ...

class CommitOffsetRequest(_message.Message):
    __slots__ = ("topic", "consumer_group", "offset")
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    CONSUMER_GROUP_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    topic: str
    consumer_group: str
    offset: int
    def __init__(self, topic: _Optional[str] = ..., consumer_group: _Optional[str] = ..., offset: _Optional[int] = ...) -> None: ...

class CommitOffsetResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StreamTopicRequest(_message.Message):
    __slots__ = ("topic", "from_offset")
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    FROM_OFFSET_FIELD_NUMBER: _ClassVar[int]
    topic: str
    from_offset: int
    def __init__(self, topic: _Optional[str] = ..., from_offset: _Optional[int] = ...) -> None: ...

class DeadLetterRequest(_message.Message):
    __slots__ = ("source_topic", "correlation_id", "failure_reason", "original_payload_json", "failure_context_json")
    SOURCE_TOPIC_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    FAILURE_REASON_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    FAILURE_CONTEXT_JSON_FIELD_NUMBER: _ClassVar[int]
    source_topic: str
    correlation_id: str
    failure_reason: str
    original_payload_json: bytes
    failure_context_json: bytes
    def __init__(self, source_topic: _Optional[str] = ..., correlation_id: _Optional[str] = ..., failure_reason: _Optional[str] = ..., original_payload_json: _Optional[bytes] = ..., failure_context_json: _Optional[bytes] = ...) -> None: ...

class DeadLetterResponse(_message.Message):
    __slots__ = ("event_id",)
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    def __init__(self, event_id: _Optional[str] = ...) -> None: ...
