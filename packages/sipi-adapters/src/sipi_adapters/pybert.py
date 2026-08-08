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
from .capabilities import AdapterCapability
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

    @classmethod
    def capability_entries(cls) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability(
                operation="link.simulate.v1",
                payload_schema="pybert.simulation.v1",
                domain_result_schemas=("pybert.native-cli-result.v1", "pybert.arrays.v1"),
                behavior_profile="default",
                role="candidate",
                execution_mode="process",
            ),
        )

    @classmethod
    def capabilities(cls, engine_instance_id: str, bundle_hash: str):
        from .capabilities import build_engine_capabilities

        return build_engine_capabilities(engine_instance_id=engine_instance_id, bundle_hash=bundle_hash, entries=cls.capability_entries())

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


class PyBertAgentSpiceResponseAdapter(CommandBuilder):
    """Strict current-drive Link execution from an existing RFM artifact pair.

    The paired Agent-Spice artifacts are materialized and hash-verified by the
    platform before this adapter runs.  The PyBERT CLI consumes them directly;
    it does not invoke Agent-Spice or turn its impedance response into a
    voltage-transfer ``ChannelResponseV1``.  S2P/S4P remains owned by the
    M4 production resolver and its explicit Python external boundary.
    """

    domain_result_schema = "pybert.agent-spice-current-driven-link-cli-result.v1"
    request_schema = "pybert.agent-spice-current-driven-link-request.v1"

    @classmethod
    def capability_entries(cls) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability(
                operation="link.simulate.v1",
                payload_schema=cls.request_schema,
                domain_result_schemas=(
                    cls.domain_result_schema,
                    "pybert.agent-spice-current-driven-link-arrays.v1",
                ),
                behavior_profile="agent-spice-current-drive",
                role="candidate",
                execution_mode="process",
            ),
        )

    @classmethod
    def capabilities(cls, engine_instance_id: str, bundle_hash: str):
        from .capabilities import build_engine_capabilities

        return build_engine_capabilities(engine_instance_id=engine_instance_id, bundle_hash=bundle_hash, entries=cls.capability_entries())

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        wire = request.to_wire()
        if wire["payload_schema"] != self.request_schema:
            raise UnsupportedCapabilityError(
                f"Agent-Spice response handoff requires payload schema {self.request_schema}"
            )
        payload = wire["payload"]
        if not isinstance(payload, Mapping) or payload.get("schema") != self.request_schema:
            raise AdapterContractError(f"payload must be a {self.request_schema} object")
        metadata = self._bound_input(request, "rfm_metadata", "agent-spice.rfm-response.v1")
        response = self._bound_input(request, "rfm_response", "agent-spice.rfm-response-binary.v1")
        input_path = workdir / "current-driven-link.json"
        input_path.write_text(json.dumps(dict(payload), sort_keys=True), encoding="utf-8")
        return [
            *invocation(bundle_path),
            "sim-agent-spice-response",
            str(input_path),
            "--rfm-metadata",
            str(workdir / metadata["relative_path"]),
            "--rfm-response",
            str(workdir / response["relative_path"]),
            "--output-dir",
            str(workdir / "out"),
        ]

    @staticmethod
    def _bound_input(
        request: BackendExecutionRequestV1,
        name: str,
        content_schema: str,
    ) -> Mapping[str, Any]:
        artifact = request["bound_inputs"].get(name)
        if not isinstance(artifact, Mapping) or artifact.get("content_schema") != content_schema:
            raise AdapterContractError(f"bound input {name!r} must have content schema {content_schema}")
        return artifact

    def build_outcome(
        self,
        request: BackendExecutionRequestV1,
        engine_entry: Mapping[str, Any],
        workdir: Path,
        process: ProcessResult,
    ) -> BackendOutcome:
        out_root = workdir / "out"
        meta_path = out_root / "meta.json"
        arrays_path = out_root / "arrays.npz"
        if not meta_path.is_file():
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine succeeded but produced no current-driven meta.json"),
                )
            )
        meta: Any = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or meta.get("schema") != self.domain_result_schema:
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine produced an invalid current-driven result schema"),
                )
            )
        meta["platform_rfm_artifacts"] = {
            name: {
                key: artifact[key]
                for key in ("relative_path", "content_schema", "sha256", "byte_length", "producer", "role")
            }
            for name, artifact in request["bound_inputs"].items()
            if name in {"rfm_metadata", "rfm_response"}
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
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
                    content_schema="pybert.agent-spice-current-driven-link-arrays.v1",
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
