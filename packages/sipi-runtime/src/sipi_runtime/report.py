"""Run-level report and compare assembly (M3-06).

``build_run_report`` assembles one deterministic report per run: per-analysis
status/attempt/artifact sections plus a comparison section whenever a
succeeded analysis used ``compare`` selection.  Domain comparators plug in as
``{profile name: ComparisonProfile}``; a small built-in profile covers the
``effective_input.sample_count`` metric used by the fake/fixture engines.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from sipi_contracts import parse_backend_execution_result

from .comparison import ComparisonProfile, Metric, compare_results
from .dag import DagPlan
from .resolution import ResolvedProject
from .supervisor_registry import SupervisorRegistry


DEFAULT_COMPARISON_PROFILES: dict[str, ComparisonProfile] = {
    "default": ComparisonProfile("default", (Metric("effective_input.sample_count"),)),
}

RESOURCE_FIELDS = ("wall_time_s", "cpu_time_s", "memory_bytes", "process_count", "artifact_bytes")


def _result_wire(domain: Any, *, role: str, engine_instance_id: str, operation: str, payload_schema: str, run_id: str, attempt_id: str, domain_result_schema: str) -> dict[str, Any]:
    return {
        "schema": "sipi.backend-execution-result.v1",
        "run_id": run_id,
        "analysis_id": "report",
        "attempt_id": attempt_id,
        "backend_execution_id": f"{attempt_id}-{role}",
        "role": role,
        "engine_instance_id": engine_instance_id,
        "bundle_hash": "sha256:report",
        "operation": operation,
        "payload_schema": payload_schema,
        "status": "succeeded",
        "domain_result_schema": domain_result_schema,
        # Synthetic bundle hash: compare_results does not consume it; M3-07/08
        # will derive it from the real stored backend execution records.
        "domain_result": domain,
        "artifacts": [],
        "events": [],
        "warnings": [],
        "timings": {},
        "resource_usage": {"actual_enforcement": {name: "unsupported" for name in RESOURCE_FIELDS}},
        "error": None,
    }


def _compare_attempt(
    *,
    analysis_id: str,
    attempt_id: str,
    run_id: str,
    artifact_root: Path,
    node_plan: Any,
    profiles: Mapping[str, ComparisonProfile],
) -> dict[str, Any]:
    selection = node_plan.selection
    profile_name = selection.get("comparison_profile", "default")
    backend_root = artifact_root / "nodes" / analysis_id / "attempts" / attempt_id / "backends"
    reference_path = backend_root / f"{attempt_id}-reference" / "out" / "meta.json"
    candidate_path = backend_root / f"{attempt_id}-candidate" / "out" / "meta.json"
    if not reference_path.is_file() or not candidate_path.is_file():
        return {"profile": profile_name, "matched": False, "errors": ["missing reference/candidate backend results"], "mismatches": []}
    profile = profiles.get(profile_name)
    if profile is None:
        return {"profile": profile_name, "matched": False, "errors": [f"unknown comparison profile: {profile_name}"], "mismatches": []}
    reference_domain = json.loads(reference_path.read_text(encoding="utf-8"))
    candidate_domain = json.loads(candidate_path.read_text(encoding="utf-8"))
    domain_result_schema = reference_domain.get("schema", "pybert.native-cli-result.v1")
    reference = parse_backend_execution_result(
        _result_wire(
            reference_domain,
            role="reference",
            engine_instance_id=selection["reference"],
            operation=node_plan.operation,
            payload_schema=node_plan.payload_schema,
            run_id=run_id,
            attempt_id=attempt_id,
            domain_result_schema=domain_result_schema,
        )
    )
    candidate = parse_backend_execution_result(
        _result_wire(
            candidate_domain,
            role="candidate",
            engine_instance_id=selection["candidate"],
            operation=node_plan.operation,
            payload_schema=node_plan.payload_schema,
            run_id=run_id,
            attempt_id=attempt_id,
            domain_result_schema=domain_result_schema,
        )
    )
    report = compare_results(reference, candidate, profile)
    return {
        "profile": report.profile,
        "matched": report.matched,
        "checked_count": report.checked_count,
        "mismatches": [
            {"path": item.path, "reference": item.reference, "candidate": item.candidate, "atol": item.atol, "rtol": item.rtol}
            for item in report.mismatches
        ],
        "errors": list(report.errors),
    }


def build_run_report(
    *,
    run_id: str,
    resolved: ResolvedProject,
    plan: DagPlan,
    registry: SupervisorRegistry,
    artifact_root: str | Path,
    comparison_profiles: Mapping[str, ComparisonProfile] | None = None,
) -> dict[str, Any]:
    profiles = dict(comparison_profiles or DEFAULT_COMPARISON_PROFILES)
    root = Path(artifact_root)
    execution = registry.get_execution(run_id)
    sections: list[dict[str, Any]] = []
    for analysis_id in plan.order:
        node = registry.get_node(run_id, analysis_id)
        attempts = registry.list_attempts(run_id, analysis_id)
        succeeded = [attempt for attempt in attempts if attempt["status"] == "succeeded"]
        artifacts: list[Any] = []
        manifest_sha256: str | None = None
        if succeeded:
            attempt = succeeded[-1]
            manifest_path = root / "nodes" / analysis_id / "attempts" / attempt["attempt_id"] / "success-manifest.json"
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                artifacts = manifest.get("artifacts", [])
                manifest_sha256 = attempt.get("success_manifest_sha256")
        section: dict[str, Any] = {
            "analysis_id": analysis_id,
            "status": node["status"] if node is not None else "unknown",
            "attempt_count": len(attempts),
            "artifacts": artifacts,
            "success_manifest_sha256": manifest_sha256,
        }
        node_plan = plan.by_id[analysis_id]
        if node_plan.selection.get("mode") == "compare" and node is not None and node["status"] == "succeeded" and succeeded:
            section["comparison"] = _compare_attempt(
                analysis_id=analysis_id,
                attempt_id=succeeded[-1]["attempt_id"],
                run_id=run_id,
                artifact_root=root,
                node_plan=node_plan,
                profiles=profiles,
            )
        sections.append(section)
    return {
        "schema": "sipi.run-report.v1",
        "run_id": run_id,
        "execution_status": execution["status"] if execution is not None else "unknown",
        "project_hash": plan.project_hash,
        "provenance": {"engine_lock_sha256": resolved.engine_lock["sha256"]},
        "analyses": sections,
    }
