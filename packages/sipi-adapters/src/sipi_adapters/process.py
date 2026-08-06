"""Hermetic process execution for strict backend adapters.

The runner verifies the engine bundle, materializes bound inputs into an
isolated per-run directory, executes the engine entrypoint with an allowlisted
environment and wall-time limit, and assembles exactly one
``BackendExecutionResultV1``.  Process-tree cancellation and hard resource
enforcement belong to M3/G2b; this layer reports Timeout/ResourceLimit states
honestly without claiming hard enforcement.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sipi_contracts import BackendExecutionRequestV1, BackendExecutionResultV1, parse_backend_execution_result

from .attestation import AttestationError, verify_wheel_bundle
from .capabilities import AdapterCapability, preflight
from .spi import AdapterContractError, UnsupportedCapabilityError, require_backend_request, validate_pinned_instance
from .venv import BundleExecutionError, install_wheel, required_console_script, resolve_console_script

ALLOWED_ENV = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "COMSPEC",
        "PATHEXT",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "OS",
    }
)
_RESOURCE_FIELDS = ("wall_time_s", "cpu_time_s", "memory_bytes", "process_count", "artifact_bytes")


class BundleVerificationError(ValueError):
    """Raised when an engine bundle cannot be verified before execution."""


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float
    timed_out: bool


@dataclass(frozen=True)
class BackendOutcome:
    """One backend result plus files that must be handed to the runtime store."""

    result: BackendExecutionResultV1
    artifact_paths: tuple[Path, ...] = ()


def platform_error(
    category: str,
    message: str,
    resource: str | None = None,
    details: Mapping[str, Any] | None = None,
    cause: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {"category": category, "message": message, "resource": resource, "cause": cause, "details": dict(details or {})}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filtered_env() -> dict[str, str]:
    env = {name: value for name, value in os.environ.items() if name in ALLOWED_ENV}
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def invocation(bundle_path: Path) -> list[str]:
    if bundle_path.suffix.lower() == ".py":
        return [sys.executable, "-I", str(bundle_path)]
    return [str(bundle_path)]


def verify_engine_bundle(engine_entry: Mapping[str, Any], repo_root: Path) -> Path:
    """Verify a pinned local bundle: wheel archives get full content attestation."""
    bundle = engine_entry["bundle"]
    if bundle["kind"] != "local_path":
        raise BundleVerificationError("https_url bundles cannot be executed without an approved downloader")
    candidate = (repo_root / bundle["path"]).resolve()
    if not candidate.is_relative_to(repo_root):
        raise BundleVerificationError("bundle path escapes the repository root")
    if not candidate.is_file():
        raise BundleVerificationError(f"engine bundle is missing: {candidate}")
    if _sha256(candidate) != bundle["sha256"]:
        raise BundleVerificationError(f"engine bundle sha256 mismatch: {candidate}")
    if candidate.suffix.lower() == ".whl":
        try:
            verify_wheel_bundle(engine_entry, repo_root)
        except AttestationError as error:
            raise BundleVerificationError(str(error)) from error
        return candidate
    manifest = engine_entry["bundle_manifest"]
    if manifest["entrypoint"] != candidate.name:
        raise BundleVerificationError("multi-file bundles are not supported yet; entrypoint must be the bundle file itself")
    entrypoints = [item for item in manifest["files"] if item["role"] == "entrypoint"]
    if (
        len(manifest["files"]) != 1
        or len(entrypoints) != 1
        or entrypoints[0]["relative_path"] != candidate.name
        or entrypoints[0]["sha256"] != bundle["sha256"]
        or entrypoints[0]["byte_length"] != candidate.stat().st_size
    ):
        raise BundleVerificationError("single-file bundle manifest must match the bundle exactly")
    return candidate


def materialize_bound_inputs(request: BackendExecutionRequestV1, repo_root: Path, workdir: Path) -> None:
    for name, artifact in request["bound_inputs"].items():
        relative = Path(artifact["relative_path"])
        source = (repo_root / relative).resolve()
        target = (workdir / relative).resolve()
        if not source.is_relative_to(repo_root):
            raise AdapterContractError(f"bound input escapes the repository root: {relative}")
        if not target.is_relative_to(workdir):
            raise AdapterContractError(f"bound input escapes the work directory: {relative}")
        if not source.is_file():
            raise AdapterContractError(f"bound input is missing: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if _sha256(target) != artifact["sha256"] or target.stat().st_size != artifact["byte_length"]:
            raise AdapterContractError(f"bound input hash mismatch: {relative}")


def run_process(
    argv: list[str],
    *,
    workdir: Path,
    env: Mapping[str, str],
    wall_time_s: float | None,
) -> ProcessResult:
    started = time.monotonic()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            argv,
            cwd=workdir,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=wall_time_s,
            creationflags=flags,
        )
        return ProcessResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            elapsed_s=time.monotonic() - started,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return ProcessResult(returncode=-1, stdout=stdout, stderr=stderr, elapsed_s=time.monotonic() - started, timed_out=True)


def assemble_backend_result(
    request: BackendExecutionRequestV1,
    *,
    status: str,
    error: Mapping[str, Any] | None = None,
    domain_result: Any = None,
    domain_result_schema: str | None = None,
    artifacts: tuple[Mapping[str, Any], ...] = (),
    warnings: tuple[str, ...] = (),
    timings: Mapping[str, Any] | None = None,
) -> BackendExecutionResultV1:
    wire: dict[str, Any] = {
        "schema": "sipi.backend-execution-result.v1",
        "run_id": request["run_id"],
        "analysis_id": request["analysis_id"],
        "attempt_id": request["attempt_id"],
        "backend_execution_id": request["backend_execution_id"],
        "role": request["role"],
        "engine_instance_id": request["engine_instance_id"],
        "bundle_hash": request["bundle_hash"],
        "operation": request["operation"],
        "payload_schema": request["payload_schema"],
        "status": status,
        "domain_result_schema": domain_result_schema,
        **({"domain_result": domain_result} if domain_result is not None else {}),
        "artifacts": list(artifacts),
        "events": [],
        "warnings": list(warnings),
        "timings": dict(timings or {}),
        "resource_usage": {"actual_enforcement": {name: "unsupported" for name in _RESOURCE_FIELDS}},
        "error": dict(error) if error is not None else None,
    }
    return parse_backend_execution_result(wire)


class CommandBuilder(Protocol):
    """Builds one engine invocation and one domain result from a run."""

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        ...

    def build_outcome(self, request: BackendExecutionRequestV1, engine_entry: Mapping[str, Any], workdir: Path, process: ProcessResult) -> BackendOutcome:
        ...


def _failed_from_error(request: BackendExecutionRequestV1, error: BaseException) -> BackendExecutionResultV1:
    message = str(error)
    cause = {"kind": type(error).__name__, "message": message}
    if isinstance(error, UnsupportedCapabilityError):
        category = "UnsupportedCapability"
    elif "escapes" in message:
        category = "InvalidRequest"
    elif "missing" in message or "hash mismatch" in message:
        category = "InputNotFound"
    else:
        category = "EngineUnavailable"
    return assemble_backend_result(request, status="failed", error=platform_error(category, message, cause=cause))


def execute_backend(
    request: BackendExecutionRequestV1,
    engine_entry: Mapping[str, Any],
    repo_root: Path,
    *,
    builder: CommandBuilder,
    workdir: Path | None = None,
    artifact_root: Path | None = None,
    capabilities: tuple[AdapterCapability, ...] | None = None,
) -> BackendExecutionResultV1:
    """Execute one strict backend execution and return its single result."""
    require_backend_request(request)
    validate_pinned_instance(request, engine_entry["instance_id"])
    if capabilities is not None:
        try:
            preflight(request, capabilities)
        except UnsupportedCapabilityError as error:
            return _failed_from_error(request, error)
    try:
        bundle_path = verify_engine_bundle(engine_entry, repo_root)
    except BundleVerificationError as error:
        return assemble_backend_result(request, status="failed", error=platform_error("EngineUnavailable", str(error)))

    owns_workdir = workdir is None
    if owns_workdir:
        workdir = Path(tempfile.mkdtemp(prefix="sipi-backend-"))
    else:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
    try:
        try:
            materialize_bound_inputs(request, repo_root, workdir)
        except AdapterContractError as error:
            return _failed_from_error(request, error)
        try:
            entry_target = bundle_path
            if bundle_path.suffix.lower() == ".whl":
                try:
                    required_console_script(engine_entry)
                    install_wheel(bundle_path, workdir / "engine-venv")
                    entry_target = resolve_console_script(engine_entry, workdir / "engine-venv")
                except BundleExecutionError as error:
                    return assemble_backend_result(
                        request,
                        status="failed",
                        error=platform_error("UnsupportedCapability", str(error)),
                    )
            argv = builder.build(request, entry_target, workdir)
        except AdapterContractError as error:
            return _failed_from_error(request, error)
        wall_time_s = request["resource_limits"].get("wall_time_s")
        process = run_process(argv, workdir=workdir, env=filtered_env(), wall_time_s=wall_time_s)
        if process.timed_out:
            return assemble_backend_result(
                request,
                status="failed",
                error=platform_error("Timeout", f"engine exceeded wall_time_s={wall_time_s}", "wall_time_s", {"sipi.adapter.elapsed-seconds": process.elapsed_s}),
            )
        if process.returncode != 0:
            message = f"engine exited with code {process.returncode}"
            if process.stderr.strip():
                message += f": {process.stderr.strip().splitlines()[-1]}"
            return assemble_backend_result(request, status="failed", error=platform_error("ExternalModelFailure", message))
        outcome = builder.build_outcome(request, engine_entry, workdir, process)
        if outcome.result["artifacts"] and artifact_root is None:
            return assemble_backend_result(
                request,
                status="failed",
                error=platform_error("InternalInvariant", "backend result has artifacts but no artifact_root was provided"),
            )
        if artifact_root is not None:
            artifact_root = Path(artifact_root)
            artifact_root.mkdir(parents=True, exist_ok=True)
            for source in outcome.artifact_paths:
                try:
                    relative = source.resolve().relative_to(workdir.resolve())
                except ValueError:
                    return assemble_backend_result(
                        request,
                        status="failed",
                        error=platform_error("InternalInvariant", f"artifact path escapes the work directory: {source}"),
                    )
                target = artifact_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            for artifact in outcome.result["artifacts"]:
                stored = artifact_root / artifact["relative_path"]
                if not stored.is_file() or _sha256(stored) != artifact["sha256"] or stored.stat().st_size != artifact["byte_length"]:
                    return assemble_backend_result(
                        request,
                        status="failed",
                        error=platform_error("InternalInvariant", f"artifact handoff verification failed: {artifact['relative_path']}"),
                    )
        return outcome.result
    finally:
        if owns_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
