"""Local execution driver (M3-05b).

The driver walks the DAG plan in topological order, runs each node through the
strict adapter SPI (``plan_backend_executions`` + ``execute_backend``),
materializes upstream success artifacts into downstream ``bound_inputs``,
publishes attempt success through the registry CAS protocol, blocks dependent
nodes on upstream failure per the project failure policy, supports bounded
automatic retry, and aggregates the execution terminal state.

Cache reuse, process-tree management, IPC-driven scheduling and restart
recovery remain later slices (M3-09); this module is a synchronous in-process
driver used by the supervisor once execution wiring is complete.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sipi_adapters import CommandBuilder, execute_backend
from sipi_contracts import RunRequestV1, parse_run_request
from sipi_contracts.json_types import thaw_json

from .dag import DagPlan
from .execution import plan_backend_executions
from .registry import EngineRegistry
from .resolution import ResolvedAnalysis, ResolvedProject
from .supervisor_registry import SupervisorRegistry


RESOURCE_LIMITS = {
    "enforcement": "monitor",
    "wall_time_s": None,
    "cpu_time_s": None,
    "memory_bytes": None,
    "process_count": None,
    "artifact_bytes": None,
}


class DriverError(RuntimeError):
    pass


@dataclass(frozen=True)
class DriverOptions:
    max_attempts: int = 1
    artifact_root: Path | None = None


def _run_request(analysis: ResolvedAnalysis, *, run_id: str, analysis_id: str, attempt_id: str, project_id: str) -> RunRequestV1:
    wire: dict[str, Any] = {
        "schema": "sipi.run-request.v1",
        "run_id": run_id,
        "project_id": project_id,
        "analysis_id": analysis_id,
        "attempt_id": attempt_id,
        "operation": analysis.operation,
        "payload_schema": analysis.payload_schema,
        "backend_selection": dict(analysis.backend_selection),
        "resource_limits": dict(RESOURCE_LIMITS),
        "randomness": {},
        "artifact_policy": {},
        "extensions": {},
    }
    if analysis.payload is not None:
        wire["payload"] = dict(analysis.payload)
    else:
        wire["payload_artifact"] = dict(analysis.payload_artifact)  # type: ignore[arg-type]
    return parse_run_request(wire)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ExecutionDriver:
    """Synchronous in-process DAG executor over a supervisor registry."""

    def __init__(self, registry: SupervisorRegistry, builders: Mapping[str, CommandBuilder], *, options: DriverOptions | None = None) -> None:
        self.registry = registry
        self.builders = dict(builders)
        self.options = options or DriverOptions()

    def run(self, resolved: ResolvedProject, plan: DagPlan, engine_registry: EngineRegistry, run_id: str) -> dict[str, Any]:
        execution = self.registry.get_execution(run_id)
        if execution is None:
            raise DriverError(f"unknown execution: {run_id}")
        if execution["status"] != "queued":
            raise DriverError(f"execution is not queued: {execution['status']}")
        artifact_root = Path(self.options.artifact_root or (Path.cwd() / "runs" / run_id))
        artifact_root.mkdir(parents=True, exist_ok=True)
        self.registry.cas_execution(run_id, execution["version"], status="resolving")
        current = self.registry.get_execution(run_id)
        self.registry.cas_execution(run_id, current["version"], status="active")
        upstream_status: dict[str, str] = {}
        upstream_artifacts: dict[str, dict[str, Mapping[str, Any]]] = {}
        for analysis_id in plan.order:
            current = self.registry.get_execution(run_id)
            if current["cancel_requested"]:
                break
            node = plan.by_id[analysis_id]
            self.registry.create_node(run_id=run_id, analysis_id=analysis_id, effective_required=node.effective_required)
            node_row = self.registry.get_node(run_id, analysis_id)
            blocked_by = [
                {"analysis_id": dependency, "terminal_status": upstream_status[dependency]}
                for dependency in node.depends_on
                if upstream_status.get(dependency) in {"failed", "cancelled", "blocked"}
            ]
            if blocked_by:
                self.registry.cas_node(run_id, analysis_id, node_row["version"], status="blocked", blocked_by=blocked_by)
                upstream_status[analysis_id] = "blocked"
                continue
            self.registry.cas_node(run_id, analysis_id, node_row["version"], status="ready")
            outcome: dict[str, Any] | None = None
            for attempt_index in range(max(1, self.options.max_attempts)):
                attempt_id = f"{analysis_id}-attempt-{attempt_index}"
                self.registry.append_attempt(attempt_id=attempt_id, run_id=run_id, analysis_id=analysis_id, retry_index=attempt_index)
                attempt_row = self.registry.get_attempt(attempt_id)
                self.registry.cas_attempt(attempt_id, attempt_row["version"], status="running")
                result = self._run_attempt(resolved, node.analysis_id, run_id, attempt_id, upstream_artifacts, engine_registry, artifact_root)
                if result["status"] == "succeeded":
                    outcome = result
                    break
                attempt_row = self.registry.get_attempt(attempt_id)
                self.registry.cas_attempt(attempt_id, attempt_row["version"], status="failed")
            if outcome is None:
                node_row = self.registry.get_node(run_id, analysis_id)
                self.registry.cas_node(run_id, analysis_id, node_row["version"], status="failed")
                upstream_status[analysis_id] = "failed"
                continue
            node_row = self.registry.get_node(run_id, analysis_id)
            self.registry.cas_node(run_id, analysis_id, node_row["version"], status="succeeded")
            upstream_status[analysis_id] = "succeeded"
            upstream_artifacts[analysis_id] = outcome["artifacts_by_role"]
        execution = self.registry.get_execution(run_id)
        if execution["cancel_requested"]:
            self.registry.cas_execution(run_id, execution["version"], status="cancelled")
            final_status = "cancelled"
        else:
            required_failed = any(
                plan.by_id[analysis_id].effective_required and upstream_status.get(analysis_id) in {"failed", "blocked"}
                for analysis_id in plan.order
            )
            final_status = "failed" if required_failed else "succeeded"
            self.registry.cas_execution(run_id, execution["version"], status=final_status)
        return {"run_id": run_id, "status": final_status, "nodes": upstream_status}

    def _run_attempt(
        self,
        resolved: ResolvedProject,
        analysis_id: str,
        run_id: str,
        attempt_id: str,
        upstream_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
        engine_registry: EngineRegistry,
        artifact_root: Path,
    ) -> dict[str, Any]:
        analysis = next(item for item in resolved.analyses if item.analysis_id == analysis_id)
        bound_inputs: dict[str, Any] = {}
        for binding in analysis.inputs:
            ref = upstream_artifacts.get(binding.from_analysis, {}).get(binding.artifact_role)
            if ref is None:
                return {"status": "failed", "reason": f"missing producer artifact role {binding.artifact_role}"}
            bound_inputs[binding.name] = dict(ref)
        run_request = _run_request(analysis, run_id=run_id, analysis_id=analysis_id, attempt_id=attempt_id, project_id=resolved.project["project"]["name"])
        try:
            plans = plan_backend_executions(run_request, engine_registry, bound_inputs=bound_inputs)
        except Exception as error:  # noqa: BLE001 - selection/preflight failures fail the attempt
            return {"status": "failed", "reason": str(error)}
        artifacts_by_role: dict[str, Mapping[str, Any]] = {}
        for plan in plans:
            backend_id = plan.request["backend_execution_id"]
            self.registry.record_backend_execution(backend_execution_id=backend_id, attempt_id=attempt_id, role=plan.role, engine_instance_id=plan.request["engine_instance_id"])
            builder = self.builders.get(plan.engine_entry["engine_family"])
            if builder is None:
                return {"status": "failed", "reason": f"no builder for engine family {plan.engine_entry['engine_family']}"}
            capabilities = builder.capability_entries() if hasattr(builder, "capability_entries") else None
            backend_root = artifact_root / "nodes" / analysis_id / "attempts" / attempt_id / "backends" / backend_id
            result = execute_backend(plan.request, plan.engine_entry, artifact_root, builder=builder, capabilities=capabilities, artifact_root=backend_root)
            if result["status"] != "succeeded":
                return {"status": "failed", "reason": f"{backend_id} {result['status']}: {result['error']}"}
            for artifact in result["artifacts"]:
                prefixed = thaw_json(dict(artifact))
                prefixed["relative_path"] = f"nodes/{analysis_id}/attempts/{attempt_id}/backends/{backend_id}/{artifact['relative_path']}"
                artifacts_by_role[artifact["role"]] = prefixed
        attempt_row = self.registry.get_attempt(attempt_id)
        self.registry.cas_attempt(attempt_id, attempt_row["version"], status="publishing")
        attempt_row = self.registry.get_attempt(attempt_id)
        manifest = {
            "schema": "sipi.success-manifest.v1",
            "run_id": run_id,
            "analysis_id": analysis_id,
            "attempt_id": attempt_id,
            "run_record_sha256": "0" * 64,
            "checksums_sha256": "0" * 64,
            "artifacts": list(artifacts_by_role.values()),
            "extensions": {},
        }
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        manifest_sha256 = _sha256_bytes(manifest_bytes)
        publish = self.registry.attempt_publish_cas(attempt_id=attempt_id, expected_version=attempt_row["version"], success_manifest_sha256=manifest_sha256)
        if publish != "committed":
            return {"status": "failed", "reason": f"publish rejected: {publish}"}
        manifest_path = artifact_root / "nodes" / analysis_id / "attempts" / attempt_id / "success-manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(manifest_bytes)
        return {"status": "succeeded", "manifest_sha256": manifest_sha256, "artifacts_by_role": artifacts_by_role}
