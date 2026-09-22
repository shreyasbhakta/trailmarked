"""Single process serving the capability registry's two external surfaces —
REST (agent invocation, mounted at /) and GraphQL (dashboard reads, mounted
at /graphql) — plus an SSE bridge over the event log's gRPC StreamTopic for
the dashboard's live event timeline, and the read-model projector that
keeps GraphQL's backing store in sync with the event log.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
from strawberry.fastapi import GraphQLRouter

from services.capability_registry.graphql_schema import schema
from services.capability_registry.projector import Projector
from services.capability_registry.rest import app as rest_app
from services.capability_registry.store import RegistryStore
from services.event_log.client import EventLogClient

app = FastAPI(title="Trailmarked Gateway")
app.mount("/api", rest_app)
app.include_router(GraphQLRouter(schema), prefix="/graphql")

_event_log = EventLogClient()
_projector = Projector(RegistryStore(), _event_log)


@app.on_event("startup")
def _start_projector() -> None:
    _projector.start()


@app.on_event("shutdown")
def _stop_projector() -> None:
    _projector.stop()


@app.get("/stream/{topic}")
async def stream_topic(topic: str, from_offset: int = 0):
    async def event_generator():
        loop = asyncio.get_event_loop()
        gen = _event_log.stream_topic(topic, from_offset)
        while True:
            event = await loop.run_in_executor(None, next, gen, None)
            if event is None:
                break
            yield {
                "event": event.event_type,
                "data": json.dumps({
                    "event_id": event.event_id, "offset": event.offset, "correlation_id": event.correlation_id,
                    "event_type": event.event_type, "occurred_at_ms": event.occurred_at_ms, "payload": event.payload,
                }),
            }

    return EventSourceResponse(event_generator())
