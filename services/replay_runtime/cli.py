"""CLI for submitting one replay run directly against the replay_runtime
gRPC service, useful for generating /evidence/ logs without going through
the REST gateway.
"""
from __future__ import annotations

import argparse
import json
import uuid

from services.replay_runtime.client import ReplayRuntimeClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capability-id", required=True)
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--input", action="append", default=[], help="key=value, repeatable")
    parser.add_argument("--idempotency-key", default=None)
    args = parser.parse_args()

    inputs = dict(pair.split("=", 1) for pair in args.input)
    idempotency_key = args.idempotency_key or f"idem_{uuid.uuid4().hex[:12]}"

    client = ReplayRuntimeClient()
    ack = client.submit_replay(capability_id=args.capability_id, tenant_id=args.tenant, idempotency_key=idempotency_key, input_params=inputs)
    status = client.get_status(ack["run_id"])
    print(json.dumps({"ack": ack, "status": status}, indent=2))


if __name__ == "__main__":
    main()
