#!/usr/bin/env bash
# Regenerates gRPC stubs from proto/ into shared/grpc_stubs/.
# After regenerating, the plain `import x_pb2` lines protoc emits in the
# generated *_grpc.py files must be rewritten to `from . import x_pb2` so
# they resolve as part of the shared.grpc_stubs package.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"

"$PYTHON" -m grpc_tools.protoc \
  -I proto \
  --python_out=shared/grpc_stubs \
  --grpc_python_out=shared/grpc_stubs \
  --pyi_out=shared/grpc_stubs \
  proto/event_log.proto proto/registry.proto proto/replay.proto proto/escalation.proto

cd shared/grpc_stubs
for name in event_log registry replay escalation; do
  sed -i '' "s/^import ${name}_pb2 as /from . import ${name}_pb2 as /" "${name}_pb2_grpc.py"
done
touch __init__.py
