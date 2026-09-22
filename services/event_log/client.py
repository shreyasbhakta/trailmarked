"""Thin typed wrapper other services use to talk to the event_log over gRPC."""
from __future__ import annotations

import json
from dataclasses import dataclass

import grpc

from shared.grpc_stubs import event_log_pb2, event_log_pb2_grpc

DEFAULT_ADDRESS = "localhost:50051"


@dataclass
class LogEvent:
    event_id: str
    topic: str
    offset: int
    correlation_id: str
    event_type: str
    occurred_at_ms: int
    payload: dict


class EventLogClient:
    def __init__(self, address: str = DEFAULT_ADDRESS):
        self._channel = grpc.insecure_channel(address)
        self._stub = event_log_pb2_grpc.EventLogStub(self._channel)

    def append(
        self,
        topic: str,
        correlation_id: str,
        event_type: str,
        payload: dict,
        producer_dedupe_key: str | None = None,
    ) -> tuple[str, int]:
        response = self._stub.Append(
            event_log_pb2.AppendRequest(
                topic=topic,
                correlation_id=correlation_id,
                event_type=event_type,
                payload_json=json.dumps(payload).encode("utf-8"),
                producer_dedupe_key=producer_dedupe_key or "",
            )
        )
        return response.event_id, response.offset

    def fetch(self, topic: str, consumer_group: str, max_events: int = 100) -> list[LogEvent]:
        response = self._stub.Fetch(
            event_log_pb2.FetchRequest(topic=topic, consumer_group=consumer_group, max_events=max_events)
        )
        return [_from_proto(e) for e in response.events]

    def commit_offset(self, topic: str, consumer_group: str, offset: int) -> None:
        self._stub.CommitOffset(
            event_log_pb2.CommitOffsetRequest(topic=topic, consumer_group=consumer_group, offset=offset)
        )

    def stream_topic(self, topic: str, from_offset: int = 0):
        for event in self._stub.StreamTopic(
            event_log_pb2.StreamTopicRequest(topic=topic, from_offset=from_offset)
        ):
            yield _from_proto(event)

    def dead_letter(
        self,
        source_topic: str,
        correlation_id: str,
        failure_reason: str,
        original_payload: dict,
        failure_context: dict,
    ) -> str:
        response = self._stub.DeadLetter(
            event_log_pb2.DeadLetterRequest(
                source_topic=source_topic,
                correlation_id=correlation_id,
                failure_reason=failure_reason,
                original_payload_json=json.dumps(original_payload).encode("utf-8"),
                failure_context_json=json.dumps(failure_context).encode("utf-8"),
            )
        )
        return response.event_id


def _from_proto(event: event_log_pb2.Event) -> LogEvent:
    return LogEvent(
        event_id=event.event_id,
        topic=event.topic,
        offset=event.offset,
        correlation_id=event.correlation_id,
        event_type=event.event_type,
        occurred_at_ms=event.occurred_at.ToMilliseconds(),
        payload=json.loads(event.payload_json.decode("utf-8")),
    )
