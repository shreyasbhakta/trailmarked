"""Boots every Trailmarked process on localhost. No Docker, no Kafka — each
service is a plain OS process talking real gRPC over loopback ports; this
script is the "orchestrator" at the scale this take-home actually needs.

    python scripts/run.py

Ctrl-C stops everything. Logs are prefixed by service name and interleaved
in this terminal; each service also logs to its own file under scripts/logs/
for anything that scrolls past.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOG_DIR = ROOT / "scripts" / "logs"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

SERVICES: list[tuple[str, list[str]]] = [
    ("event_log", [PYTHON, "-m", "services.event_log.server"]),
    ("capability_registry_grpc", [PYTHON, "-m", "services.capability_registry.server"]),
    ("escalation_saga", [PYTHON, "-m", "services.escalation_saga.server"]),
    ("replay_runtime", [PYTHON, "-m", "services.replay_runtime.server"]),
    ("gateway", [PYTHON, "-m", "uvicorn", "services.capability_registry.gateway:app", "--port", "8000"]),
    ("mock_bank_app", [PYTHON, "-m", "uvicorn", "mock_bank_app.main:app", "--port", "4000"]),
]

# Each subsequent service depends on the one(s) before it being listening
# (gRPC clients connect lazily, but staggering start avoids a burst of
# connection-refused log noise on first boot).
STARTUP_STAGGER_S = 0.6


def _stream_output(name: str, proc: subprocess.Popen, log_file) -> None:
    for line in proc.stdout:
        sys.stdout.write(f"[{name}] {line}")
        log_file.write(line)
        log_file.flush()


def main() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT), "GRPC_ENABLE_FORK_SUPPORT": "0"}

    processes: list[subprocess.Popen] = []
    threads: list[threading.Thread] = []
    log_files = []

    def shutdown(*_args) -> None:
        print("\nshutting down...")
        for proc in processes:
            proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        for f in log_files:
            f.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for name, cmd in SERVICES:
        log_file = open(LOG_DIR / f"{name}.log", "w")
        log_files.append(log_file)
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(proc)
        thread = threading.Thread(target=_stream_output, args=(name, proc, log_file), daemon=True)
        thread.start()
        threads.append(thread)
        print(f"started {name} (pid {proc.pid})")
        time.sleep(STARTUP_STAGGER_S)

    print("\nall services up:")
    print("  REST      http://localhost:8000/api")
    print("  GraphQL   http://localhost:8000/graphql")
    print("  SSE       http://localhost:8000/stream/{topic}")
    print("  mock bank http://localhost:4000/default/members  and  /overlay_demo/members")
    print("\nCtrl-C to stop.\n")

    for proc in processes:
        proc.wait()


if __name__ == "__main__":
    main()
