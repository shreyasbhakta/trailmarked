from __future__ import annotations

import logging
import time
from concurrent import futures

import grpc

from services.event_log.storage import EventStore
from shared.grpc_stubs import event_log_pb2, event_log_pb2_grpc

logger = logging.getLogger("event_log")

DEFAULT_PORT = 50051
STREAM_POLL_INTERVAL_S = 0.5


class EventLogServicer(event_log_pb2_grpc.EventLogServicer):
    def __init__(self, store: EventStore):
        self._store = store

    def Append(self, request, context):
        event_id, offset = self._store.append(
            topic=request.topic,
            correlation_id=request.correlation_id,
            event_type=request.event_type,
            payload_json=request.payload_json,
            producer_dedupe_key=request.producer_dedupe_key or None,
        )
        logger.info(
            "appended topic=%s offset=%d event_type=%s correlation_id=%s",
            request.topic, offset, request.event_type, request.correlation_id,
        )
        return event_log_pb2.AppendResponse(event_id=event_id, offset=offset)

    def Fetch(self, request, context):
        events = self._store.fetch(request.topic, request.consumer_group, request.max_events or 100)
        return event_log_pb2.FetchResponse(events=[_to_proto_event(e) for e in events])

    def CommitOffset(self, request, context):
        self._store.commit_offset(request.topic, request.consumer_group, request.offset)
        return event_log_pb2.CommitOffsetResponse()

    def StreamTopic(self, request, context):
        offset = request.from_offset
        while context.is_active():
            events = self._store.fetch_from(request.topic, offset)
            for event in events:
                yield _to_proto_event(event)
                offset = event.offset + 1
            time.sleep(STREAM_POLL_INTERVAL_S)

    def DeadLetter(self, request, context):
        event_id = self._store.dead_letter(
            source_topic=request.source_topic,
            correlation_id=request.correlation_id,
            failure_reason=request.failure_reason,
            original_payload_json=request.original_payload_json,
            failure_context_json=request.failure_context_json,
        )
        logger.warning(
            "dead-lettered source_topic=%s correlation_id=%s reason=%s",
            request.source_topic, request.correlation_id, request.failure_reason,
        )
        return event_log_pb2.DeadLetterResponse(event_id=event_id)


def _to_proto_event(stored) -> event_log_pb2.Event:
    proto_event = event_log_pb2.Event(
        event_id=stored.event_id,
        topic=stored.topic,
        offset=stored.offset,
        correlation_id=stored.correlation_id,
        event_type=stored.event_type,
        payload_json=stored.payload_json.encode("utf-8"),
    )
    proto_event.occurred_at.FromMilliseconds(stored.occurred_at_ms)
    return proto_event


def serve(port: int = DEFAULT_PORT) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    event_log_pb2_grpc.add_EventLogServicer_to_server(EventLogServicer(EventStore()), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("event_log listening on :%d", port)
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    server = serve()
    server.wait_for_termination()
