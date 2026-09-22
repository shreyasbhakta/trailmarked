from __future__ import annotations

import logging
from concurrent import futures

import grpc

from services.capability_registry import compiler
from services.capability_registry.overlay import resolve as resolve_overlay
from services.capability_registry.store import RegistryStore
from services.event_log.client import EventLogClient
from shared.grpc_stubs import registry_pb2, registry_pb2_grpc
from shared.schemas import CapabilityArtifact, TenantOverlay

logger = logging.getLogger("capability_registry.grpc")

DEFAULT_PORT = 50052

_COMPATIBILITY_TO_PROTO = {
    "BACKWARD": registry_pb2.BACKWARD,
    "FORWARD": registry_pb2.FORWARD,
    "BREAKING": registry_pb2.BREAKING,
}


class CapabilityRegistryServicer(registry_pb2_grpc.CapabilityRegistryServicer):
    def __init__(self, store: RegistryStore, event_log: EventLogClient):
        self._store = store
        self._event_log = event_log

    def CompileCapability(self, request, context):
        artifact = compiler.compile_capability(
            discovery_run_id=request.discovery_run_id,
            capability_id=request.capability_id,
            tenant_id=request.tenant_id,
            store=self._store,
            event_log=self._event_log,
        )
        return registry_pb2.CompileResponse(
            capability_id=artifact.capability_id,
            version=artifact.version,
            compatibility=_COMPATIBILITY_TO_PROTO[artifact.compatibility.value],
        )

    def GetCapability(self, request, context):
        row = (
            self._store.get_version(request.capability_id, request.version, "*")
            if request.version
            else self._store.latest_version(request.capability_id, "*")
        )
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, f"capability {request.capability_id} not found")
        return registry_pb2.Capability(
            capability_id=request.capability_id,
            version=row["version"],
            compatibility=_COMPATIBILITY_TO_PROTO[row["compatibility"]],
            tenant_scope="*",
            artifact_json=row["artifact_json"].encode("utf-8"),
        )

    def ResolveForTenant(self, request, context):
        row = (
            self._store.get_version(request.capability_id, request.version, "*")
            if request.version
            else self._store.latest_version(request.capability_id, "*")
        )
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, f"capability {request.capability_id} not found")
        base = CapabilityArtifact.model_validate_json(row["artifact_json"])

        overlay_dict = self._store.get_overlay(request.tenant_id, request.capability_id)
        overlay = TenantOverlay.model_validate(overlay_dict) if overlay_dict else None
        resolved = resolve_overlay(base, overlay)

        return registry_pb2.Capability(
            capability_id=resolved.capability_id,
            version=resolved.version,
            compatibility=_COMPATIBILITY_TO_PROTO[resolved.compatibility.value],
            tenant_scope=resolved.tenant_scope,
            artifact_json=resolved.model_dump_json().encode("utf-8"),
        )

    def ListCapabilities(self, request, context):
        return registry_pb2.ListResponse(
            capabilities=[
                registry_pb2.CapabilitySummary(
                    capability_id=c["capability_id"], latest_version=c["latest_version"], name=c["capability_id"]
                )
                for c in self._store.list_capabilities()
            ]
        )

    def GetVersionHistory(self, request, context):
        return registry_pb2.VersionHistoryResponse(
            versions=[
                registry_pb2.CapabilityVersionEntry(
                    version=v["version"],
                    compatibility=_COMPATIBILITY_TO_PROTO[v["compatibility"]],
                    discovery_run_id=v["discovery_run_id"],
                )
                for v in self._store.version_history(request.capability_id)
            ]
        )


def serve(port: int = DEFAULT_PORT) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    registry_pb2_grpc.add_CapabilityRegistryServicer_to_server(
        CapabilityRegistryServicer(RegistryStore(), EventLogClient()), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("capability_registry gRPC listening on :%d", port)
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    server = serve()
    server.wait_for_termination()
