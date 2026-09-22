from __future__ import annotations

import json

import grpc

from shared.grpc_stubs import registry_pb2, registry_pb2_grpc

DEFAULT_ADDRESS = "localhost:50052"

_COMPATIBILITY_FROM_PROTO = {0: "UNKNOWN", 1: "BACKWARD", 2: "FORWARD", 3: "BREAKING"}


class CapabilityRegistryClient:
    def __init__(self, address: str = DEFAULT_ADDRESS):
        self._channel = grpc.insecure_channel(address)
        self._stub = registry_pb2_grpc.CapabilityRegistryStub(self._channel)

    def compile_capability(self, discovery_run_id: str, capability_id: str, tenant_id: str) -> dict:
        response = self._stub.CompileCapability(
            registry_pb2.CompileRequest(discovery_run_id=discovery_run_id, capability_id=capability_id, tenant_id=tenant_id)
        )
        return {
            "capability_id": response.capability_id,
            "version": response.version,
            "compatibility": _COMPATIBILITY_FROM_PROTO[response.compatibility],
        }

    def resolve_for_tenant(self, capability_id: str, tenant_id: str, version: int = 0) -> dict:
        response = self._stub.ResolveForTenant(
            registry_pb2.ResolveRequest(capability_id=capability_id, tenant_id=tenant_id, version=version)
        )
        return json.loads(response.artifact_json.decode("utf-8"))

    def get_capability(self, capability_id: str, version: int = 0) -> dict:
        response = self._stub.GetCapability(registry_pb2.GetCapabilityRequest(capability_id=capability_id, version=version))
        return json.loads(response.artifact_json.decode("utf-8"))

    def list_capabilities(self) -> list[dict]:
        response = self._stub.ListCapabilities(registry_pb2.ListRequest())
        return [
            {"capability_id": c.capability_id, "latest_version": c.latest_version, "name": c.name}
            for c in response.capabilities
        ]
