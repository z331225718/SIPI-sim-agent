"""Persistent local supervisor daemon entry point (M3-05a).

``python -m sipi_runtime.supervisor_main --data-dir <dir>`` acquires the
singleton lock, reconciles stale state, binds the local IPC endpoint and keeps
serving until SIGINT/SIGTERM.  ``spawn_supervisor`` launches that daemon
detached from the invoking CLI and waits until ``ping`` succeeds.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .supervisor import Supervisor
from .supervisor_ipc import SupervisorClient, SupervisorServer, SupervisorUnavailable


def serve(data_dir: str | Path, *, reconcile: bool = True) -> None:
    """Run the supervisor until SIGINT/SIGTERM; never returns normally."""
    root = Path(data_dir)
    supervisor = Supervisor(root)
    if reconcile:
        supervisor.reconcile()
    stop = threading.Event()
    server = SupervisorServer(supervisor, root, on_shutdown=stop.set)
    server.start()

    def _stop(*_: object) -> None:
        stop.set()

    try:
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
    except ValueError:
        pass
    while not stop.is_set():
        stop.wait(1.0)
    server.close()


def spawn_supervisor(data_dir: str | Path, *, timeout_s: float = 20.0, poll_s: float = 0.2) -> subprocess.Popen:
    """Launch the detached daemon and wait until its IPC endpoint is ready."""
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "sipi_runtime.supervisor_main", "--data-dir", str(root)]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    client = SupervisorClient(root)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            client.ping()
            return process
        except SupervisorUnavailable:
            time.sleep(poll_s)
    process.terminate()
    raise SupervisorUnavailable(f"supervisor daemon did not become ready in {root}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sipi-supervisor")
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args(argv)
    serve(args.data_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
