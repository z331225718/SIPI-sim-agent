"""In-memory lifecycle rules for one project execution.

This module deliberately owns only transition integrity.  Durable coordination,
reconciliation, process supervision, and dependency scheduling belong to M3.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from sipi_contracts import SipiRunEventV1, SuccessManifestV1, parse_run_event

ExecutionStatus = Literal["queued", "resolving", "active", "succeeded", "failed", "cancelled"]
NodeStatus = Literal["pending", "ready", "active", "succeeded", "failed", "cancelled", "blocked"]
AttemptStatus = Literal["queued", "validating", "staging", "running", "publishing", "succeeded", "failed", "cancelled"]
TerminalNodeStatus = Literal["succeeded", "failed", "cancelled", "blocked"]
AttemptOutcome = Literal["succeeded", "failed", "cancelled"]

_TERMINAL_NODES = frozenset({"succeeded", "failed", "cancelled", "blocked"})
_TERMINAL_ATTEMPTS = frozenset({"succeeded", "failed", "cancelled"})
_ATTEMPT_NEXT = {
    "queued": "validating",
    "validating": "staging",
    "staging": "running",
    "running": "publishing",
}


class InvalidTransition(ValueError):
    """Raised when a command would violate a lifecycle invariant."""


class CancellationToken:
    """Read-only cooperative cancellation signal for a single attempt."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def requested(self) -> bool:
        return self._event.is_set()


class _CancellationSource:
    """The lifecycle's private authority for changing a cancellation token."""

    def __init__(self) -> None:
        self.token = CancellationToken()
        self._lock = threading.Lock()

    def request(self) -> bool:
        with self._lock:
            if self.token._event.is_set():
                return False
            self.token._event.set()
            return True


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot:
    run_id: str
    execution_status: ExecutionStatus
    cancel_requested: bool
    degraded: bool
    warnings: tuple[str, ...]
    nodes: Mapping[str, Mapping[str, Any]]
    attempts: Mapping[str, Mapping[str, Any]]


class InMemoryEventSink:
    """Serializes canonical platform events for one project execution."""

    def __init__(self, run_id: str, *, clock: Callable[[], float]) -> None:
        self._run_id = run_id
        self._clock = clock
        self._started_at = clock()
        self._last_elapsed = 0.0
        self._sequence = 0
        self._events: list[SipiRunEventV1] = []
        self._lock = threading.RLock()

    @property
    def run_id(self) -> str:
        return self._run_id

    def emit(
        self,
        *,
        scope: Literal["project", "analysis", "attempt", "backend_execution"],
        stage: str,
        analysis_id: str | None = None,
        attempt_id: str | None = None,
        backend_execution_id: str | None = None,
        progress: Mapping[str, float] | None = None,
    ) -> SipiRunEventV1:
        with self._lock:
            elapsed = max(self._last_elapsed, self._clock() - self._started_at, 0.0)
            event = parse_run_event(
                {
                    "schema": "sipi.run-event.v1",
                    "run_id": self._run_id,
                    "sequence": self._sequence,
                    "scope": scope,
                    "stage": stage,
                    "elapsed_s": elapsed,
                    "analysis_id": analysis_id,
                    "attempt_id": attempt_id,
                    "backend_execution_id": backend_execution_id,
                    **({"progress": dict(progress)} if progress is not None else {}),
                    "extensions": {},
                },
                producer=True,
            )
            self._events.append(event)
            self._sequence += 1
            self._last_elapsed = elapsed
            return event

    def events(self) -> tuple[SipiRunEventV1, ...]:
        with self._lock:
            return tuple(self._events)


class InMemoryLifecycle:
    """Thread-safe, single-process state machine for a project execution.

    The caller supplies already-resolved DAG nodes.  This aggregate never
    publishes artifacts and is not a durable coordination authority.
    """

    def __init__(
        self,
        run_id: str,
        node_specs: Mapping[str, bool | Mapping[str, bool]],
        *,
        event_sink: InMemoryEventSink | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be a non-empty string")
        if not node_specs:
            raise ValueError("at least one DAG node is required")
        if event_sink is not None and clock is not None:
            raise ValueError("pass either event_sink or clock, not both")

        self._lock = threading.RLock()
        self._run_id = run_id
        self._execution: ExecutionStatus = "queued"
        self._degraded = False
        self._warnings: list[str] = []
        self._project_cancel_requested = False
        self._analysis_cancel_requested: set[str] = set()
        self._nodes = {node_id: self._new_node(node_id, spec) for node_id, spec in node_specs.items()}
        if not any(node["effective_required"] for node in self._nodes.values()):
            raise ValueError("at least one node must be effective_required")
        self._attempts: dict[str, dict[str, Any]] = {}
        self._cancel_sources: dict[str, _CancellationSource] = {}
        self._event_sink = event_sink or InMemoryEventSink(run_id, clock=clock or __import__("time").monotonic)
        if self._event_sink.run_id != run_id:
            raise ValueError("event sink run_id must match lifecycle run_id")

    @staticmethod
    def _new_node(node_id: str, spec: bool | Mapping[str, bool]) -> dict[str, Any]:
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node IDs must be non-empty strings")
        if isinstance(spec, Mapping):
            allowed = {"required", "effective_required"}
            unknown = set(spec) - allowed
            if unknown:
                raise ValueError(f"unknown node spec fields: {sorted(unknown)}")
            required = spec.get("required", True)
            effective_required = spec.get("effective_required", required)
            if not isinstance(required, bool) or not isinstance(effective_required, bool):
                raise ValueError("node required flags must be booleans")
        elif isinstance(spec, bool):
            required = spec
            effective_required = spec
        else:
            raise ValueError("node spec must be a boolean or mapping")
        if required and not effective_required:
            raise ValueError("required nodes must be effective_required")
        return {
            "status": "pending",
            "required": required,
            "effective_required": effective_required,
            "attempts": [],
            "blocked_by": (),
            "cache_hit": False,
            "cancel_requested": False,
        }

    @property
    def event_sink(self) -> InMemoryEventSink:
        return self._event_sink

    @property
    def run_id(self) -> str:
        return self._run_id

    def _require_execution(self, *allowed: ExecutionStatus) -> None:
        if self._execution not in allowed:
            raise InvalidTransition(f"execution {self._execution} is not one of {allowed}")

    def _node(self, node_id: str) -> dict[str, Any]:
        try:
            return self._nodes[node_id]
        except KeyError as error:
            raise InvalidTransition(f"unknown node: {node_id}") from error

    def _attempt(self, attempt_id: str) -> dict[str, Any]:
        try:
            return self._attempts[attempt_id]
        except KeyError as error:
            raise InvalidTransition(f"unknown attempt: {attempt_id}") from error

    def _cancel_is_accepted(self, node_id: str) -> bool:
        return self._project_cancel_requested or node_id in self._analysis_cancel_requested

    def _emit(self, stage: str, *, node_id: str | None = None, attempt_id: str | None = None) -> None:
        if attempt_id is not None:
            self._event_sink.emit(scope="attempt", stage=stage, analysis_id=node_id, attempt_id=attempt_id)
        elif node_id is not None:
            self._event_sink.emit(scope="analysis", stage=stage, analysis_id=node_id)
        else:
            self._event_sink.emit(scope="project", stage=stage)

    def start_resolving(self) -> None:
        with self._lock:
            self._require_execution("queued")
            self._emit("execution.resolving")
            self._execution = "resolving"

    def activate_execution(self) -> None:
        with self._lock:
            self._require_execution("resolving")
            if self._project_cancel_requested:
                raise InvalidTransition("a cancelled execution may not become active")
            self._emit("execution.active")
            self._execution = "active"

    def mark_node_ready(self, node_id: str) -> None:
        with self._lock:
            self._require_execution("active")
            node = self._node(node_id)
            if node["status"] != "pending":
                raise InvalidTransition(f"node {node_id} cannot become ready from {node['status']}")
            self._emit("analysis.ready", node_id=node_id)
            node["status"] = "ready"

    def start_attempt(self, node_id: str, attempt_id: str) -> CancellationToken:
        with self._lock:
            self._require_execution("active")
            if not isinstance(attempt_id, str) or not attempt_id:
                raise ValueError("attempt_id must be a non-empty string")
            node = self._node(node_id)
            if node["status"] not in {"ready", "active"}:
                raise InvalidTransition(f"node {node_id} cannot start an attempt from {node['status']}")
            if self._project_cancel_requested or node_id in self._analysis_cancel_requested:
                raise InvalidTransition("cancelled nodes may not start new attempts")
            if attempt_id in self._attempts:
                raise InvalidTransition(f"duplicate attempt: {attempt_id}")
            if any(self._attempts[item]["status"] not in _TERMINAL_ATTEMPTS for item in node["attempts"]):
                raise InvalidTransition(f"node {node_id} already has an active attempt")
            source = _CancellationSource()
            self._emit("attempt.queued", node_id=node_id, attempt_id=attempt_id)
            node["status"] = "active"
            node["attempts"].append(attempt_id)
            self._attempts[attempt_id] = {"node_id": node_id, "status": "queued", "error_category": None, "cancel_requested": False}
            self._cancel_sources[attempt_id] = source
            return source.token

    def advance_attempt(self, attempt_id: str, stage: AttemptStatus) -> None:
        with self._lock:
            self._require_execution("active")
            attempt = self._attempt(attempt_id)
            expected = _ATTEMPT_NEXT.get(attempt["status"])
            if expected != stage:
                raise InvalidTransition(f"attempt {attempt_id} cannot advance from {attempt['status']} to {stage}")
            if self._cancel_is_accepted(attempt["node_id"]):
                raise InvalidTransition("cancelled attempts may not advance")
            self._emit(f"attempt.{stage}", node_id=attempt["node_id"], attempt_id=attempt_id)
            attempt["status"] = stage

    def finish_attempt(self, attempt_id: str, outcome: AttemptOutcome, *, retry_allowed: bool = False) -> None:
        with self._lock:
            self._require_execution("active")
            if outcome not in {"succeeded", "failed", "cancelled"}:
                raise ValueError("outcome must be succeeded, failed, or cancelled")
            attempt = self._attempt(attempt_id)
            if attempt["status"] in _TERMINAL_ATTEMPTS:
                raise InvalidTransition(f"attempt {attempt_id} is already terminal")
            node = self._node(attempt["node_id"])
            if outcome == "succeeded":
                if attempt["status"] != "publishing":
                    raise InvalidTransition("attempt may only succeed from publishing")
                if self._cancel_is_accepted(attempt["node_id"]):
                    raise InvalidTransition("a cancelled attempt may not publish success")
                attempt_status: AttemptStatus = "succeeded"
                node_status: NodeStatus = "succeeded"
                error_category = None
            elif outcome == "cancelled" and not self._cancel_is_accepted(attempt["node_id"]):
                # A backend may not convert an arbitrary result into a user cancellation.
                attempt_status = "failed"
                node_status = "failed"
                error_category = "EngineProtocolFailure"
            elif self._cancel_is_accepted(attempt["node_id"]):
                attempt_status = "cancelled"
                node_status = "cancelled"
                error_category = None
                late_backend_outcome = outcome if outcome != "cancelled" else None
            elif outcome == "failed":
                attempt_status = "failed"
                node_status = "active" if retry_allowed else "failed"
                error_category = None
                late_backend_outcome = None
            else:
                attempt_status = "cancelled"
                node_status = "cancelled"
                error_category = None
                late_backend_outcome = None
            if outcome == "succeeded" or (outcome == "cancelled" and not self._cancel_is_accepted(attempt["node_id"])):
                late_backend_outcome = None
            self._emit(f"attempt.{attempt_status}", node_id=attempt["node_id"], attempt_id=attempt_id)
            attempt["status"] = attempt_status
            attempt["error_category"] = error_category
            if late_backend_outcome is not None:
                attempt["late_backend_outcome"] = late_backend_outcome
            node["status"] = node_status

    def mark_cache_hit(self, node_id: str, success_manifest: SuccessManifestV1) -> None:
        with self._lock:
            self._require_execution("active")
            node = self._node(node_id)
            if node["status"] != "ready" or node["attempts"]:
                raise InvalidTransition("cache hit requires a ready node with no attempts")
            if not isinstance(success_manifest, SuccessManifestV1):
                raise TypeError("cache hits require a validated SuccessManifestV1")
            if success_manifest["analysis_id"] != node_id:
                raise InvalidTransition("success manifest does not belong to this analysis")
            self._emit("analysis.cache_hit", node_id=node_id)
            node["status"] = "succeeded"
            node["cache_hit"] = True
            node["success_manifest"] = success_manifest.wire

    def block_node(self, node_id: str, *, blocked_by: tuple[str, ...]) -> None:
        with self._lock:
            self._require_execution("active")
            node = self._node(node_id)
            if node["status"] not in {"pending", "ready"} or node["attempts"]:
                raise InvalidTransition("blocked is only valid before an attempt exists")
            if not blocked_by or len(set(blocked_by)) != len(blocked_by) or node_id in blocked_by:
                raise InvalidTransition("blocked_by must name distinct non-self terminal nodes")
            for blocker_id in blocked_by:
                blocker = self._node(blocker_id)
                if blocker["status"] not in {"failed", "cancelled", "blocked"}:
                    raise InvalidTransition("blockers must already be failed, cancelled, or blocked")
            self._emit("analysis.blocked", node_id=node_id)
            node["status"] = "blocked"
            node["blocked_by"] = tuple(blocked_by)

    def request_cancel(self, node_id: str | None = None) -> Literal["accepted", "already_requested", "already_terminal"]:
        with self._lock:
            if self._execution in {"succeeded", "failed", "cancelled"}:
                return "already_terminal"
            if self._execution == "queued":
                if node_id is not None:
                    raise InvalidTransition("analysis cancellation requires a resolved execution")
                self._emit("execution.resolving")
                self._execution = "resolving"
            if node_id is None:
                if self._project_cancel_requested:
                    return "already_requested"
                targets = tuple(self._nodes)
                stage = "execution.cancel_requested"
            else:
                node = self._node(node_id)
                if node_id in self._analysis_cancel_requested:
                    return "already_requested"
                if node["status"] in _TERMINAL_NODES:
                    return "already_terminal"
                targets = (node_id,)
                stage = "analysis.cancel_requested"

            self._emit(stage, node_id=node_id)
            if node_id is None:
                self._project_cancel_requested = True
            else:
                self._analysis_cancel_requested.add(node_id)
            for target_id in targets:
                node = self._nodes[target_id]
                if node["status"] in _TERMINAL_NODES:
                    continue
                node["cancel_requested"] = True
                active_attempts = [item for item in node["attempts"] if self._attempts[item]["status"] not in _TERMINAL_ATTEMPTS]
                if active_attempts:
                    for attempt_id in active_attempts:
                        self._attempts[attempt_id]["cancel_requested"] = True
                        self._cancel_sources[attempt_id].request()
                else:
                    node["status"] = "cancelled"
            return "accepted"

    def finalize_execution(self) -> ExecutionStatus:
        with self._lock:
            self._require_execution("resolving", "active")
            if any(node["status"] not in _TERMINAL_NODES for node in self._nodes.values()):
                raise InvalidTransition("execution cannot finish before DAG quiescence")

            required = [node for node in self._nodes.values() if node["effective_required"]]
            required_cancelled = any(
                node["status"] == "cancelled" or node_id in self._analysis_cancel_requested
                for node_id, node in self._nodes.items()
                if node["effective_required"]
            )
            required_failed = any(node["status"] in {"failed", "blocked"} for node in required)
            optional_degraded = any(
                not node["effective_required"] and node["status"] in {"failed", "cancelled", "blocked"}
                for node in self._nodes.values()
            )
            if self._project_cancel_requested or required_cancelled:
                terminal: ExecutionStatus = "cancelled"
            elif required_failed:
                terminal = "failed"
            else:
                terminal = "succeeded"
            self._emit(f"execution.{terminal}")
            self._degraded = optional_degraded
            self._warnings = ["optional DAG nodes did not complete successfully"] if optional_degraded else []
            self._execution = terminal
            return terminal

    def fail_resolution(self) -> None:
        """Terminate an unresolved execution when DAG resolution itself fails."""
        with self._lock:
            self._require_execution("resolving")
            required_cancelled = any(
                node_id in self._analysis_cancel_requested and node["effective_required"]
                for node_id, node in self._nodes.items()
            )
            terminal: ExecutionStatus = "cancelled" if self._project_cancel_requested or required_cancelled else "failed"
            self._emit(f"execution.{terminal}")
            self._execution = terminal

    def snapshot(self) -> LifecycleSnapshot:
        with self._lock:
            nodes = {
                node_id: MappingProxyType({**node, "attempts": tuple(node["attempts"]), "blocked_by": tuple(node["blocked_by"])})
                for node_id, node in self._nodes.items()
            }
            attempts = {attempt_id: MappingProxyType(dict(attempt)) for attempt_id, attempt in self._attempts.items()}
            return LifecycleSnapshot(
                run_id=self.run_id,
                execution_status=self._execution,
                cancel_requested=self._project_cancel_requested,
                degraded=self._degraded,
                warnings=tuple(self._warnings),
                nodes=MappingProxyType(nodes),
                attempts=MappingProxyType(attempts),
            )
