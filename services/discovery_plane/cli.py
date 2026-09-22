"""CLI entrypoint for running one discovery run end-to-end.

Example:
    python -m services.discovery_plane.cli \\
        --goal "Look up member 1001 and report their current balance" \\
        --capability-id member_balance_lookup \\
        --tenant default \\
        --base-url http://localhost:4000/default/members

On RunSucceeded, calls the capability registry over gRPC to compile the
event stream into a trailmarked capability.
"""
from __future__ import annotations

import argparse
import json
import logging

from services.discovery_plane.loop import DiscoveryRun
from services.capability_registry.client import CapabilityRegistryClient

logger = logging.getLogger("discovery_plane.cli")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", required=True)
    parser.add_argument("--capability-id", required=True)
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--input", action="append", default=[], help="key=value, repeatable")
    parser.add_argument("--compile", action="store_true", default=True)
    parser.add_argument("--no-compile", dest="compile", action="store_false")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    inputs = dict(pair.split("=", 1) for pair in args.input)
    run = DiscoveryRun(
        goal=args.goal, capability_id=args.capability_id, tenant_id=args.tenant, base_url=args.base_url, inputs=inputs
    )
    result = run.execute()
    print(json.dumps(result, indent=2))

    if result["status"] == "RunSucceeded" and args.compile:
        registry = CapabilityRegistryClient()
        compiled = registry.compile_capability(
            discovery_run_id=result["run_id"], capability_id=args.capability_id, tenant_id=args.tenant
        )
        print(json.dumps(compiled, indent=2))


if __name__ == "__main__":
    main()
