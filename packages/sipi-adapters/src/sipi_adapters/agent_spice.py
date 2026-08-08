"""Agent-Spice process adapters (M2-01 / M3-07b)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sipi_contracts import BackendExecutionRequestV1, BackendExecutionResultV1

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


class AgentSpiceHspiceAdapter(CommandBuilder):
    """circuit.solve.v1 over the Agent-Spice ``run-hspice`` CLI.

    The engine entrypoint must be the pinned single-file bundle; multi-file
    wheels and native DLL closures arrive in a later M2 slice.  The domain
    result is the engine's ``run_summary.json`` for the first executed case.
    """

    domain_result_schema = "agent-spice.hspice-run-summary.v1"

    @classmethod
    def capability_entries(cls) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability(
                operation="circuit.solve.v1",
                payload_schema="agent-spice.hspice.v1",
                domain_result_schemas=("agent-spice.hspice-run-summary.v1",),
                behavior_profile="default",
                role="reference",
                execution_mode="process",
            ),
        )

    @classmethod
    def capabilities(cls, engine_instance_id: str, bundle_hash: str):
        from .capabilities import build_engine_capabilities

        return build_engine_capabilities(engine_instance_id=engine_instance_id, bundle_hash=bundle_hash, entries=cls.capability_entries())

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        payload = request["payload"]
        deck = payload.get("deck")
        backend = payload.get("backend", "native")
        if not isinstance(deck, str) or not deck:
            raise AdapterContractError("payload requires a deck path relative to the work directory")
        if backend not in {"native", "ngspice", "xyce", "xyce-xdm"}:
            raise UnsupportedCapabilityError(f"unsupported backend: {backend!r}")
        deck_path = (workdir / deck).resolve()
        if not deck_path.is_relative_to(workdir.resolve()):
            raise AdapterContractError("deck path escapes the work directory")
        if not deck_path.is_file():
            raise AdapterContractError(f"deck input is missing: {deck}")
        return [
            *invocation(bundle_path),
            "run-hspice",
            str(deck_path),
            "--backend",
            backend,
            "--output-root",
            str(workdir / "out"),
            "--execute",
        ]

    def build_outcome(self, request: BackendExecutionRequestV1, engine_entry: Mapping[str, Any], workdir: Path, process: ProcessResult) -> BackendOutcome:
        out_root = workdir / "out"
        summaries = sorted(out_root.rglob("run_summary.json"))
        if not summaries:
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine succeeded but produced no run_summary.json"),
                )
            )
        summary: Any = json.loads(summaries[0].read_text(encoding="utf-8"))
        warnings: tuple[str, ...] = ()
        if len(summaries) > 1:
            warnings = (f"multiple run_summary.json files found; used {summaries[0].relative_to(workdir).as_posix()}",)
        return BackendOutcome(
            assemble_backend_result(
                request,
                status="succeeded",
                domain_result=summary,
                domain_result_schema=self.domain_result_schema,
                warnings=warnings,
            )
        )

class AgentSpiceRfmResponseAdapter(CommandBuilder):
    """circuit.solve.v1 over the Agent-Spice native ``rfm-response`` CLI.

    The engine entrypoint is the pinned native ``agent-spice-sim`` executable.
    The payload names an RFM model file (relative to the work directory) plus
    the FFT size; the engine writes a frequency-major complex response binary
    and a ``agent-spice.rfm-response.v1`` metadata document, which is the
    domain result handed to the runtime artifact store.
    """

    domain_result_schema = "agent-spice.rfm-response.v1"

    @classmethod
    def capability_entries(cls) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability(
                operation="circuit.solve.v1",
                payload_schema="sipi.adapter.agent-spice.rfm-response-request.v1",
                domain_result_schemas=("agent-spice.rfm-response.v1",),
                behavior_profile="default",
                role="reference",
                execution_mode="process",
            ),
        )

    @classmethod
    def capabilities(cls, engine_instance_id: str, bundle_hash: str):
        from .capabilities import build_engine_capabilities

        return build_engine_capabilities(engine_instance_id=engine_instance_id, bundle_hash=bundle_hash, entries=cls.capability_entries())

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        payload = request.to_wire()["payload"]
        rfm = payload.get("rfm")
        fft_size = payload.get("fft_size")
        dt = payload.get("dt")
        if not isinstance(rfm, str) or not rfm:
            raise AdapterContractError("payload requires an rfm path relative to the work directory")
        if not isinstance(fft_size, int) or fft_size <= 0:
            raise AdapterContractError("payload requires a positive integer fft_size")
        if not isinstance(dt, (int, float)) or dt <= 0:
            raise AdapterContractError("payload requires a positive dt in seconds")
        rfm_path = (workdir / rfm).resolve()
        if not rfm_path.is_relative_to(workdir.resolve()):
            raise AdapterContractError("rfm path escapes the work directory")
        if not rfm_path.is_file():
            raise AdapterContractError(f"rfm model is missing: {rfm}")
        out_dir = workdir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        argv = [
            *invocation(bundle_path),
            "rfm-response",
            str(rfm_path),
            "--fft-size",
            str(fft_size),
            "--dt",
            format(float(dt), ".17g"),
            "--response-bin",
            str(out_dir / "response.bin"),
            "--metadata-json",
            str(out_dir / "meta.json"),
        ]
        return argv

    def build_outcome(self, request: BackendExecutionRequestV1, engine_entry: Mapping[str, Any], workdir: Path, process: ProcessResult) -> BackendOutcome:
        out_root = workdir / "out"
        meta_path = out_root / "meta.json"
        response_path = out_root / "response.bin"
        if not meta_path.is_file():
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine succeeded but produced no rfm-response metadata"),
                )
            )
        meta: Any = json.loads(meta_path.read_text(encoding="utf-8"))
        artifacts: list[dict[str, Any]] = [
            {
                "schema": "sipi.artifact-ref.v1",
                "content_schema": self.domain_result_schema,
                "relative_path": "out/meta.json",
                "mime_type": "application/json",
                "sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest(),
                "byte_length": meta_path.stat().st_size,
                "producer": request["engine_instance_id"],
                "role": "rfm-response",
                "extensions": {},
            }
        ]
        artifact_paths = [meta_path]
        if response_path.is_file():
            artifacts.append(
                {
                    "schema": "sipi.artifact-ref.v1",
                    "content_schema": "agent-spice.rfm-response-binary.v1",
                    "relative_path": "out/response.bin",
                    "mime_type": "application/octet-stream",
                    "sha256": hashlib.sha256(response_path.read_bytes()).hexdigest(),
                    "byte_length": response_path.stat().st_size,
                    "producer": request["engine_instance_id"],
                    "role": "data",
                    "extensions": {},
                }
            )
            artifact_paths.append(response_path)
        return BackendOutcome(
            assemble_backend_result(
                request,
                status="succeeded",
                domain_result=meta,
                domain_result_schema=self.domain_result_schema,
                artifacts=tuple(artifacts),
            ),
            artifact_paths=tuple(artifact_paths),
        )
