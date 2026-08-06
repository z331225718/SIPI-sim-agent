"""PyBERT strict link adapters (M2-02)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sipi_contracts import BackendExecutionRequestV1

from .process import (
    BackendOutcome,
    CommandBuilder,
    ProcessResult,
    assemble_backend_result,
    invocation,
    platform_error,
)
from .spi import AdapterContractError, UnsupportedCapabilityError


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_ref(
    *,
    relative_path: str,
    content_schema: str,
    mime_type: str,
    path: Path,
    producer: str,
    role: str,
) -> dict[str, Any]:
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": content_schema,
        "relative_path": relative_path,
        "mime_type": mime_type,
        "sha256": _sha256(path),
        "byte_length": path.stat().st_size,
        "producer": producer,
        "role": role,
        "extensions": {},
    }


class PyBertNativeAdapter(CommandBuilder):
    """link.simulate.v1 over the strict PyBERT ``sim-native`` CLI.

    The payload carries an inline SimulationInputV1 document; the engine writes
    ``meta.json`` (schema ``pybert.native-cli-result.v1``) and ``arrays.npz``
    into the output directory, which are handed to the runtime artifact store.
    This adapter never calls PyBERT's auto/compare entry points.
    """

    domain_result_schema = "pybert.native-cli-result.v1"

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        wire = request.to_wire()
        if wire.get("payload_artifact") is not None:
            raise UnsupportedCapabilityError("payload_artifact handoff is a later M2 slice")
        payload = wire["payload"]
        simulation_input = payload.get("simulation_input")
        if not isinstance(simulation_input, Mapping):
            raise AdapterContractError("payload requires an inline simulation_input object")
        input_path = workdir / "input.json"
        input_path.write_text(json.dumps(simulation_input, sort_keys=True), encoding="utf-8")
        return [
            *invocation(bundle_path),
            "sim-native",
            str(input_path),
            "--output-dir",
            str(workdir / "out"),
        ]

    def build_outcome(self, request: BackendExecutionRequestV1, engine_entry: Mapping[str, Any], workdir: Path, process: ProcessResult) -> BackendOutcome:
        out_root = workdir / "out"
        meta_path = out_root / "meta.json"
        arrays_path = out_root / "arrays.npz"
        if not meta_path.is_file():
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine succeeded but produced no meta.json"),
                )
            )
        meta: Any = json.loads(meta_path.read_text(encoding="utf-8"))
        artifacts = [
            _artifact_ref(
                relative_path="out/meta.json",
                content_schema=self.domain_result_schema,
                mime_type="application/json",
                path=meta_path,
                producer=request["engine_instance_id"],
                role="domain_result",
            )
        ]
        if arrays_path.is_file():
            artifacts.append(
                _artifact_ref(
                    relative_path="out/arrays.npz",
                    content_schema="pybert.arrays.v1",
                    mime_type="application/octet-stream",
                    path=arrays_path,
                    producer=request["engine_instance_id"],
                    role="data",
                )
            )
        return BackendOutcome(
            assemble_backend_result(
                request,
                status="succeeded",
                domain_result=meta,
                domain_result_schema=self.domain_result_schema,
                artifacts=tuple(artifacts),
            ),
            artifact_paths=(meta_path, arrays_path) if arrays_path.is_file() else (meta_path,),
        )
