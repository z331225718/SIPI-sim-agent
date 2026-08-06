"""Backend execution assembly (M2-08 integration).

The runtime turns one run request into pinned backend executions: selection
hash and bundle hash are injected, engine instance and role are fixed, and
adapter boundaries receive only ``BackendExecutionRequestV1`` documents.
Compare mode yields exactly two executions (reference + candidate); auto mode
yields one execution after stable-candidate fallback.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sipi_contracts import BackendExecutionRequestV1, RunRequestV1, parse_backend_execution_request

from .registry import EngineRegistry
from .selection import resolve_selection


@dataclass(frozen=True)
class PlannedExecution:
    role: str
    request: BackendExecutionRequestV1
    engine_entry: Mapping[str, Any]


def plan_backend_executions(
    run_request: RunRequestV1,
    registry: EngineRegistry,
    *,
    allow_internal: bool = False,
    bound_inputs: Mapping[str, Any] | None = None,
) -> tuple[PlannedExecution, ...]:
    """Resolve the selection and build one backend request per pinned engine."""
    wire = run_request.to_wire()
    trace = resolve_selection(wire["backend_selection"], registry, allow_internal=allow_internal)
    payload_artifact = wire.get("payload_artifact")
    plans: list[PlannedExecution] = []
    for resolved in trace.resolved:
        request_wire: dict[str, Any] = {
            "schema": "sipi.backend-execution-request.v1",
            "run_id": wire["run_id"],
            "analysis_id": wire["analysis_id"],
            "attempt_id": wire["attempt_id"],
            "backend_execution_id": f"{wire['attempt_id']}-{resolved.role}",
            "role": resolved.role,
            "engine_instance_id": resolved.instance_id,
            "bundle_hash": "sha256:" + resolved.engine_entry["bundle"]["sha256"],
            "operation": wire["operation"],
            "payload_schema": wire["payload_schema"],
            "bound_inputs": dict(bound_inputs or {}),
            "resource_limits": wire["resource_limits"],
            "artifact_policy": wire["artifact_policy"],
            "randomness": wire["randomness"],
            "selection_hash": trace.selection_hash,
        }
        if payload_artifact is not None:
            request_wire["payload_artifact"] = payload_artifact
        else:
            request_wire["payload"] = wire["payload"]
        request = parse_backend_execution_request(request_wire)
        plans.append(PlannedExecution(role=resolved.role, request=request, engine_entry=resolved.engine_entry))
    return tuple(plans)
