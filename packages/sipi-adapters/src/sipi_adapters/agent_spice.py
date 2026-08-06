"""Agent-Spice process adapters (M2-01)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from sipi_contracts import BackendExecutionRequestV1, BackendExecutionResultV1

from .process import (
    CommandBuilder,
    ProcessResult,
    assemble_backend_result,
    invocation,
    platform_error,
)
from .spi import AdapterContractError


class AgentSpiceHspiceAdapter(CommandBuilder):
    """circuit.solve.v1 over the Agent-Spice ``run-hspice`` CLI.

    The engine entrypoint must be the pinned single-file bundle; multi-file
    wheels and native DLL closures arrive in a later M2 slice.  The domain
    result is the engine's ``run_summary.json`` for the first executed case.
    """

    domain_result_schema = "agent-spice.hspice-run-summary.v1"

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        payload = request["payload"]
        deck = payload.get("deck")
        backend = payload.get("backend", "native")
        if not isinstance(deck, str) or not deck:
            raise AdapterContractError("payload requires a deck path relative to the work directory")
        if backend not in {"native", "ngspice", "xyce", "xyce-xdm"}:
            raise AdapterContractError(f"unsupported backend: {backend!r}")
        deck_path = workdir / deck
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

    def build_result(self, request: BackendExecutionRequestV1, engine_entry: Mapping[str, Any], workdir: Path, process: ProcessResult) -> BackendExecutionResultV1:
        out_root = workdir / "out"
        summaries = sorted(out_root.rglob("run_summary.json"))
        if not summaries:
            return assemble_backend_result(
                request,
                status="failed",
                error=platform_error("ExternalModelFailure", "engine succeeded but produced no run_summary.json"),
            )
        summary: Any = json.loads(summaries[0].read_text(encoding="utf-8"))
        warnings: tuple[str, ...] = ()
        if len(summaries) > 1:
            warnings = (f"multiple run_summary.json files found; used {summaries[0].relative_to(workdir).as_posix()}",)
        return assemble_backend_result(
            request,
            status="succeeded",
            domain_result=summary,
            domain_result_schema=self.domain_result_schema,
            warnings=warnings,
        )
