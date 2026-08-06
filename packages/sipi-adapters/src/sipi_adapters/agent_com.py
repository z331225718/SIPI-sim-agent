"""Agent-COM process adapters (M2-03)."""

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
from .spi import AdapterContractError


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


def _resolve_input(workdir: Path, relative: str, *, label: str) -> Path:
    candidate = (workdir / relative).resolve()
    if not candidate.is_relative_to(workdir.resolve()):
        raise AdapterContractError(f"{label} path escapes the work directory")
    if not candidate.is_file():
        raise AdapterContractError(f"{label} input is missing: {relative}")
    return candidate


class AgentComRunAdapter(CommandBuilder):
    """com.r480.run.v1 over the ``com8023 run`` CLI.

    Inputs (XLSX/Touchstone) are materialized bound inputs referenced by the
    payload; the engine writes ``result.json``, ``diagnostics.npz`` and
    ``report.html``, which are handed to the runtime artifact store.
    """

    domain_result_schema = "agent-com.result-v1"

    @classmethod
    def capability_entries(cls) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability(
                operation="com.r480.run.v1",
                payload_schema="agent-com.r480.v1",
                domain_result_schemas=("agent-com.result-v1", "agent-com.diagnostics.v1"),
                behavior_profile="r480",
                role="reference",
                execution_mode="process",
                external_model_capabilities={
                    "sipi.adapter.artifact-roles": {
                        "domain_result": ["result.json"],
                        "data": ["diagnostics.npz"],
                        "report": ["report.html"],
                    }
                },
            ),
        )

    @classmethod
    def capabilities(cls, engine_instance_id: str, bundle_hash: str):
        from .capabilities import build_engine_capabilities

        return build_engine_capabilities(engine_instance_id=engine_instance_id, bundle_hash=bundle_hash, entries=cls.capability_entries())

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        payload = request.to_wire()["payload"]
        config = payload.get("config")
        thru = payload.get("thru")
        if not isinstance(config, str) or not isinstance(thru, str):
            raise AdapterContractError("payload requires config and thru paths relative to the work directory")
        config_path = _resolve_input(workdir, config, label="config")
        thru_path = _resolve_input(workdir, thru, label="thru")
        argv = [
            *invocation(bundle_path),
            "run",
            "--config",
            str(config_path),
            "--thru",
            str(thru_path),
            "--output-dir",
            str(workdir / "out"),
        ]
        for name in ("fext", "next"):
            for relative in payload.get(name, []) or []:
                if not isinstance(relative, str):
                    raise AdapterContractError(f"{name} entries must be strings")
                argv += [f"--{name}", str(_resolve_input(workdir, relative, label=name))]
        if payload.get("no_plots"):
            argv.append("--no-plots")
        return argv

    def build_outcome(self, request: BackendExecutionRequestV1, engine_entry: Mapping[str, Any], workdir: Path, process: ProcessResult) -> BackendOutcome:
        out_root = workdir / "out"
        result_path = out_root / "result.json"
        if not result_path.is_file():
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine succeeded but produced no result.json"),
                )
            )
        domain_result: Any = json.loads(result_path.read_text(encoding="utf-8"))
        artifacts = [
            _artifact_ref(
                relative_path="out/result.json",
                content_schema=self.domain_result_schema,
                mime_type="application/json",
                path=result_path,
                producer=request["engine_instance_id"],
                role="domain_result",
            )
        ]
        produced = [result_path]
        for name, role, content_schema, mime_type in (
            ("diagnostics.npz", "data", "agent-com.diagnostics.v1", "application/octet-stream"),
            ("report.html", "report", "text/html", "text/html"),
        ):
            path = out_root / name
            if path.is_file():
                artifacts.append(
                    _artifact_ref(
                        relative_path=f"out/{name}",
                        content_schema=content_schema,
                        mime_type=mime_type,
                        path=path,
                        producer=request["engine_instance_id"],
                        role=role,
                    )
                )
                produced.append(path)
        return BackendOutcome(
            assemble_backend_result(
                request,
                status="succeeded",
                domain_result=domain_result,
                domain_result_schema=self.domain_result_schema,
                artifacts=tuple(artifacts),
            ),
            artifact_paths=tuple(produced),
        )
