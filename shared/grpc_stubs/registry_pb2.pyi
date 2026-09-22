import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Compatibility(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN: _ClassVar[Compatibility]
    BACKWARD: _ClassVar[Compatibility]
    FORWARD: _ClassVar[Compatibility]
    BREAKING: _ClassVar[Compatibility]
UNKNOWN: Compatibility
BACKWARD: Compatibility
FORWARD: Compatibility
BREAKING: Compatibility

class CompileRequest(_message.Message):
    __slots__ = ("discovery_run_id", "capability_id", "tenant_id")
    DISCOVERY_RUN_ID_FIELD_NUMBER: _ClassVar[int]
    CAPABILITY_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    discovery_run_id: str
    capability_id: str
    tenant_id: str
    def __init__(self, discovery_run_id: _Optional[str] = ..., capability_id: _Optional[str] = ..., tenant_id: _Optional[str] = ...) -> None: ...

class CompileResponse(_message.Message):
    __slots__ = ("capability_id", "version", "compatibility")
    CAPABILITY_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    COMPATIBILITY_FIELD_NUMBER: _ClassVar[int]
    capability_id: str
    version: int
    compatibility: Compatibility
    def __init__(self, capability_id: _Optional[str] = ..., version: _Optional[int] = ..., compatibility: _Optional[_Union[Compatibility, str]] = ...) -> None: ...

class GetCapabilityRequest(_message.Message):
    __slots__ = ("capability_id", "version")
    CAPABILITY_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    capability_id: str
    version: int
    def __init__(self, capability_id: _Optional[str] = ..., version: _Optional[int] = ...) -> None: ...

class ResolveRequest(_message.Message):
    __slots__ = ("capability_id", "tenant_id", "version")
    CAPABILITY_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    capability_id: str
    tenant_id: str
    version: int
    def __init__(self, capability_id: _Optional[str] = ..., tenant_id: _Optional[str] = ..., version: _Optional[int] = ...) -> None: ...

class ListRequest(_message.Message):
    __slots__ = ("tenant_id",)
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    def __init__(self, tenant_id: _Optional[str] = ...) -> None: ...

class ListResponse(_message.Message):
    __slots__ = ("capabilities",)
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    capabilities: _containers.RepeatedCompositeFieldContainer[CapabilitySummary]
    def __init__(self, capabilities: _Optional[_Iterable[_Union[CapabilitySummary, _Mapping]]] = ...) -> None: ...

class CapabilitySummary(_message.Message):
    __slots__ = ("capability_id", "latest_version", "name", "risk_level")
    CAPABILITY_ID_FIELD_NUMBER: _ClassVar[int]
    LATEST_VERSION_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    RISK_LEVEL_FIELD_NUMBER: _ClassVar[int]
    capability_id: str
    latest_version: int
    name: str
    risk_level: int
    def __init__(self, capability_id: _Optional[str] = ..., latest_version: _Optional[int] = ..., name: _Optional[str] = ..., risk_level: _Optional[int] = ...) -> None: ...

class VersionHistoryRequest(_message.Message):
    __slots__ = ("capability_id",)
    CAPABILITY_ID_FIELD_NUMBER: _ClassVar[int]
    capability_id: str
    def __init__(self, capability_id: _Optional[str] = ...) -> None: ...

class VersionHistoryResponse(_message.Message):
    __slots__ = ("versions",)
    VERSIONS_FIELD_NUMBER: _ClassVar[int]
    versions: _containers.RepeatedCompositeFieldContainer[CapabilityVersionEntry]
    def __init__(self, versions: _Optional[_Iterable[_Union[CapabilityVersionEntry, _Mapping]]] = ...) -> None: ...

class CapabilityVersionEntry(_message.Message):
    __slots__ = ("version", "compatibility", "compiled_at", "discovery_run_id")
    VERSION_FIELD_NUMBER: _ClassVar[int]
    COMPATIBILITY_FIELD_NUMBER: _ClassVar[int]
    COMPILED_AT_FIELD_NUMBER: _ClassVar[int]
    DISCOVERY_RUN_ID_FIELD_NUMBER: _ClassVar[int]
    version: int
    compatibility: Compatibility
    compiled_at: _timestamp_pb2.Timestamp
    discovery_run_id: str
    def __init__(self, version: _Optional[int] = ..., compatibility: _Optional[_Union[Compatibility, str]] = ..., compiled_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., discovery_run_id: _Optional[str] = ...) -> None: ...

class Capability(_message.Message):
    __slots__ = ("capability_id", "version", "compatibility", "tenant_scope", "artifact_json")
    CAPABILITY_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    COMPATIBILITY_FIELD_NUMBER: _ClassVar[int]
    TENANT_SCOPE_FIELD_NUMBER: _ClassVar[int]
    ARTIFACT_JSON_FIELD_NUMBER: _ClassVar[int]
    capability_id: str
    version: int
    compatibility: Compatibility
    tenant_scope: str
    artifact_json: bytes
    def __init__(self, capability_id: _Optional[str] = ..., version: _Optional[int] = ..., compatibility: _Optional[_Union[Compatibility, str]] = ..., tenant_scope: _Optional[str] = ..., artifact_json: _Optional[bytes] = ...) -> None: ...
