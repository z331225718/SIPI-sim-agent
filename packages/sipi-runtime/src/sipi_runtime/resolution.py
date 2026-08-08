"""Project path resolution and input hashing (M3-02).

``resolve_project`` turns a validated ``sipi.project.v1`` document into a
read-only resolved project: every platform-level relative path is verified
inside the project root and hashed, each analysis receives a complete
discriminated backend selection (own override or ``runtime.backend_defaults``),
and inline payloads/artifacts get deterministic input hashes.  Domain payload
objects are never rewritten.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sipi_contracts import ContractViolation, ProjectV1
from sipi_contracts.validation import resolve_artifact_path


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _artifact_ref(root: Path, relative_path: str, content_schema: str, role: str, producer: str) -> dict[str, Any]:
    resolved = resolve_artifact_path(root, {"relative_path": relative_path}, must_exist=True)
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": content_schema,
        "relative_path": relative_path,
        "mime_type": "application/json" if resolved.suffix.lower() == ".json" else "application/octet-stream",
        "sha256": _sha256_file(resolved),
        "byte_length": resolved.stat().st_size,
        "producer": producer,
        "role": role,
        "extensions": {},
    }


@dataclass(frozen=True)
class ResolvedInputBinding:
    name: str
    from_analysis: str
    artifact_role: str
    expected_schema: str


@dataclass(frozen=True)
class ResolvedAnalysis:
    analysis_id: str
    operation: str
    payload_schema: str
    payload: Mapping[str, Any] | None
    payload_artifact: Mapping[str, Any] | None
    payload_sha256: str
    backend_selection: Mapping[str, Any]
    selection_source: str
    depends_on: tuple[str, ...]
    required: bool
    inputs: tuple[ResolvedInputBinding, ...]
    static_inputs: Mapping[str, Mapping[str, Any]]
    exports: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class ResolvedProject:
    """Read-only resolved project with pinned input hashes and selections."""

    project: ProjectV1
    project_hash: str
    engine_lock: Mapping[str, Any]
    failure_policy: str
    analyses: tuple[ResolvedAnalysis, ...]

    def _content_wire(self) -> dict[str, Any]:
        """Wire without ``project_hash``; the hash is defined over this content."""
        return {
            "schema": "sipi.project-resolved.v1",
            "project": self.project["project"]["name"],
            "engine_lock": dict(self.engine_lock),
            "failure_policy": self.failure_policy,
            "analyses": [
                {
                    "analysis_id": analysis.analysis_id,
                    "operation": analysis.operation,
                    "payload_schema": analysis.payload_schema,
                    "payload": dict(analysis.payload) if analysis.payload is not None else None,
                    "payload_sha256": analysis.payload_sha256,
                    "payload_artifact": dict(analysis.payload_artifact) if analysis.payload_artifact is not None else None,
                    "backend_selection": dict(analysis.backend_selection),
                    "selection_source": analysis.selection_source,
                    "depends_on": list(analysis.depends_on),
                    "required": analysis.required,
                    "inputs": [
                        {
                            "name": binding.name,
                            "from_analysis": binding.from_analysis,
                            "artifact_role": binding.artifact_role,
                            "expected_schema": binding.expected_schema,
                        }
                        for binding in analysis.inputs
                    ],
                    "static_inputs": {name: dict(ref) for name, ref in analysis.static_inputs.items()},
                    "exports": [dict(export) for export in analysis.exports],
                }
                for analysis in self.analyses
            ],
        }

    def to_wire(self) -> dict[str, Any]:
        return {**self._content_wire(), "project_hash": self.project_hash}


def resolve_project(project: ProjectV1, root: str | Path) -> ResolvedProject:
    """Resolve every platform path, hash inputs, and pin complete selections."""
    project_root = Path(root).resolve(strict=True)
    wire = project.to_wire()
    engine_lock = _artifact_ref(
        project_root,
        wire["runtime"]["engine_lock"],
        content_schema="sipi.engine-lock.v1",
        role="engine_lock",
        producer="project",
    )
    defaults: Mapping[str, Any] = wire["runtime"].get("backend_defaults", {})
    resolved_analyses: list[ResolvedAnalysis] = []
    for index, analysis in enumerate(wire["analyses"]):
        pointer = f"/analyses/{index}"
        operation = analysis["operation"]
        selection = analysis.get("backend_selection")
        if selection is not None:
            selection_source = "analysis"
        elif operation in defaults:
            selection = defaults[operation]
            selection_source = "runtime_default"
        else:
            raise ContractViolation("sipi.project.v1", "missing_selection", pointer, f"analysis {analysis['id']} has no backend_selection and no runtime default for {operation}")
        assert isinstance(selection, Mapping)
        payload = analysis.get("payload")
        payload_artifact = analysis.get("payload_artifact")
        if payload is not None:
            payload_sha256 = _sha256_bytes(_canonical_json(payload))
            artifact_ref: Mapping[str, Any] | None = None
        else:
            assert isinstance(payload_artifact, str)
            artifact_ref = _artifact_ref(
                project_root,
                payload_artifact,
                content_schema=analysis["payload_schema"],
                role="payload",
                producer=analysis["id"],
            )
            payload_sha256 = artifact_ref["sha256"]
        resolved_analyses.append(
            ResolvedAnalysis(
                analysis_id=analysis["id"],
                operation=operation,
                payload_schema=analysis["payload_schema"],
                payload=payload,
                payload_artifact=artifact_ref,
                payload_sha256=payload_sha256,
                backend_selection=dict(selection),
                selection_source=selection_source,
                depends_on=tuple(analysis.get("depends_on", [])),
                required=bool(analysis.get("required", True)),
                inputs=tuple(
                    ResolvedInputBinding(name=name, **binding)
                    for name, binding in analysis.get("inputs", {}).items()
                ),
                static_inputs={
                    name: _artifact_ref(
                        project_root,
                        relative,
                        content_schema=f"sipi.static-input.v1",
                        role="static-input",
                        producer=analysis["id"],
                    )
                    for name, relative in analysis.get("static_inputs", {}).items()
                },
                exports=tuple(analysis.get("exports", [])),
            )
        )
    resolved = ResolvedProject(
        project=project,
        project_hash="",
        engine_lock=engine_lock,
        failure_policy=wire.get("failure_policy", "block-dependents, continue-independent"),
        analyses=tuple(resolved_analyses),
    )
    project_hash = _sha256_bytes(_canonical_json(resolved._content_wire()))
    return ResolvedProject(
        project=project,
        project_hash=project_hash,
        engine_lock=engine_lock,
        failure_policy=resolved.failure_policy,
        analyses=resolved.analyses,
    )
