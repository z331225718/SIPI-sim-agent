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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sipi_adapters import PyBertNativeAdapter
from sipi_contracts import parse_project

from .driver import DriverOptions, ExecutionDriver
from .registry import EngineRegistry, load_engine_lock
from .dag import plan_dag
from .resolution import resolve_project
from .supervisor import Supervisor
from .supervisor_ipc import SupervisorClient, SupervisorServer, SupervisorUnavailable


def build_runner(supervisor: Supervisor, data_dir: str | Path):
    """Build the submit runner that drives one execution through the DAG driver."""

    def runner(project_root: str, project_path: str, run_id: str) -> None:
        try:
            execution = supervisor.registry.get_execution(run_id)
            if execution is None:
                return
            if execution["status"] not in {"succeeded", "failed", "cancelled"}:
                now = datetime.now(timezone.utc)
                supervisor.registry.cas_execution(
                    run_id,
                    execution["version"],
                    lease_owner="supervisor-1",
                    lease_expires_at=(now + timedelta(seconds=300)).isoformat(),
                    heartbeat_at=now.isoformat(),
                )
            project_dir = Path(project_root)
            resolved = resolve_project(parse_project((project_dir / project_path).read_text(encoding="utf-8")), project_dir)
            execution = supervisor.registry.get_execution(run_id)
            if resolved.project_hash != execution["project_hash"]:
                supervisor.registry.cas_execution(run_id, execution["version"], status="failed")
                return
            engine_registry = EngineRegistry(load_engine_lock(project_dir / resolved.engine_lock["relative_path"]))
            plan = plan_dag(resolved, engine_registry)
            ExecutionDriver(
                supervisor.registry,
                {"pybert": PyBertNativeAdapter()},
                options=DriverOptions(artifact_root=project_dir),
            ).run(resolved, plan, engine_registry, run_id)
        except Exception as error:  # noqa: BLE001 - runner failure must settle the execution row
            execution = supervisor.registry.get_execution(run_id)
            if execution is not None and execution["status"] not in {"succeeded", "failed", "cancelled"}:
                try:
                    supervisor.registry.cas_execution(run_id, execution["version"], status="failed")
                except Exception:  # noqa: BLE001 - best-effort settle
                    pass

    return runner


def serve(data_dir: str | Path, *, reconcile: bool = True) -> None:
    """Run the supervisor until SIGINT/SIGTERM; never returns normally."""
    root = Path(data_dir)
    supervisor = Supervisor(root)
    if reconcile:
        supervisor.reconcile()
    stop = threading.Event()
    server = SupervisorServer(supervisor, root, on_shutdown=stop.set, runner=build_runner(supervisor, root))
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
