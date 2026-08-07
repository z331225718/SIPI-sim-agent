"""Local single-user supervisor IPC (M3-04b3).

Transport uses the standard-library ``multiprocessing.connection`` channel:
Windows ``AF_PIPE`` (current-user named pipe, ``\\\\.\\pipe\\...``) and POSIX
``AF_UNIX`` (Unix domain socket).  Messages are length-framed JSON bytes (no
pickle), keeping the surface small and local-only.  The server binds only
after acquiring the supervisor singleton lock; the client raises
``SupervisorUnavailable`` when no supervisor is listening.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import Any

from .supervisor import Supervisor, SupervisorLock


class SupervisorUnavailable(RuntimeError):
    """Raised when the supervisor IPC endpoint cannot be reached."""


def ipc_family() -> str:
    return "AF_PIPE" if os.name == "nt" else "AF_UNIX"


def ipc_address(data_dir: str | Path) -> str:
    root = Path(data_dir).resolve()
    if os.name == "nt":
        digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
        return rf"\\.\pipe\sipi-supervisor-{digest}"
    return str(root / "supervisor.ipc")


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class SupervisorServer:
    """Accepts one local client connection at a time and dispatches commands."""

    def __init__(
        self,
        supervisor: Supervisor,
        data_dir: str | Path,
        *,
        on_shutdown: Any = None,
        runner: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.supervisor: Supervisor | None = supervisor
        self._on_shutdown = on_shutdown
        self._runner = runner
        self.data_dir = Path(data_dir)
        self.family = ipc_family()
        self.address = ipc_address(self.data_dir)
        self._lock: SupervisorLock | None = None
        self._listener: Listener | None = None
        self._stopped = False
        self._thread: threading.Thread | None = None

    def start(self) -> "SupervisorServer":
        if self._lock is None:
            self._lock = SupervisorLock(self.data_dir)
            self._lock.acquire()
        self._listener = Listener(self.address, family=self.family)
        self._thread = threading.Thread(target=self._accept_loop, name="sipi-supervisor-ipc", daemon=True)
        self._thread.start()
        return self

    def _accept_loop(self) -> None:
        while not self._stopped:
            try:
                connection = self._listener.accept()  # type: ignore[union-attr]
            except OSError:
                break
            self._handle(connection)

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        command = request.get("command")
        if command == "ping":
            return {"ok": True, "pid": os.getpid()}
        if command == "submit":
            execution = self.supervisor.registry.submit_execution(
                run_id=request["run_id"],
                project_hash=request["project_hash"],
                submission_key=request["submission_key"],
                failure_policy=request["failure_policy"],
                retry_of=request.get("retry_of"),
            )
            if self._runner is not None and request.get("project_root") and request.get("project_path"):
                threading.Thread(
                    target=self._runner,
                    args=(request["project_root"], request["project_path"], execution["run_id"]),
                    name="sipi-supervisor-runner",
                    daemon=True,
                ).start()
            return {"ok": True, "execution": execution}
        if command == "status":
            return {"ok": True, "execution": self.supervisor.registry.get_execution(request["run_id"])}
        if command == "cancel":
            status, affected = self.supervisor.request_cancel(run_id=request["run_id"], analysis_id=request.get("analysis_id"))
            return {"ok": True, "status": status, "affected": list(affected)}
        if command == "shutdown":
            if self._on_shutdown is None:
                return {"ok": False, "error": {"category": "UnsupportedCapability", "message": "shutdown is not enabled on this server"}}
            self._on_shutdown()
            return {"ok": True}
        return {"ok": False, "error": {"category": "InvalidRequest", "message": f"unknown command: {command!r}"}}

    def _handle(self, connection: Any) -> None:
        try:
            payload = connection.recv_bytes()
            request = json.loads(payload.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = self._dispatch(request)
        except Exception as error:  # noqa: BLE001 - server must answer every connection
            response = {"ok": False, "error": {"category": "InternalInvariant", "message": str(error)}}
        try:
            connection.send_bytes(_encode(response))
        finally:
            connection.close()

    def close(self) -> None:
        self._stopped = True
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        if self._lock is not None:
            self._lock.release()
            self._lock = None
        if self.supervisor is not None:
            self.supervisor.close()
            self.supervisor = None

    def __enter__(self) -> "SupervisorServer":
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.close()


class SupervisorClient:
    """Thin JSON client for status/submit/cancel over the same local transport."""

    def __init__(self, data_dir: str | Path, *, timeout_s: float = 10.0) -> None:
        self.family = ipc_family()
        self.address = ipc_address(data_dir)
        self.timeout_s = timeout_s

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            connection = Client(self.address, family=self.family)
        except (OSError, EOFError) as error:
            raise SupervisorUnavailable(f"no supervisor listening at {self.address}") from error
        try:
            connection.send_bytes(_encode(payload))
            response = json.loads(connection.recv_bytes().decode("utf-8"))
        finally:
            connection.close()
        if not isinstance(response, dict):
            raise SupervisorUnavailable("supervisor returned a non-object response")
        return response

    def ping(self) -> dict[str, Any]:
        return self.request({"command": "ping"})
