"""Run the selected matched-S21 profile through the product CLI externally.

The harness is oracle-only. It materializes the selected S2P Git blob in
temporary custody, sends it to a clean-built ``sipi channel run --stdin``, and
retains only hashes, metadata, and comparison metrics in its report.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import platform
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from compare_channel_s2p_matched import (
    ComparatorError,
    _array_hash,
    _cargo_executable,
    _compare,
    _git_bytes,
    _load,
    _sha256_bytes,
    _sha256_file,
    _scrubbed_environment,
    _safe_archive_member,
    observer_kernel,
    parse_two_port_touchstone_ri,
    verify_document,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.required-profile-cli-compare.v1"
PROFILE_ID = "channel-s2p-channel-16ghz-3db-v1"
REQUEST_SCHEMA = "sipi.channel.matched-two-port-kernel-run-request.v1"
RESULT_SCHEMA = "sipi.channel.matched-two-port-kernel-run-result.v1"


class CliComparatorError(RuntimeError):
    """Raised when the external CLI acceptance gate cannot prove conformance."""


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CliComparatorError(f"{label} must be finite")
    return float(value)


def _strict_json(payload: bytes, label: str) -> dict[str, Any]:
    if not payload.endswith(b"\n") or payload.count(b"\n") != 1 or b"\r" in payload:
        raise CliComparatorError(f"{label} must be one LF-terminated JSON line")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise CliComparatorError(f"{label} contains a duplicate JSON field")
            result[key] = value
        return result

    try:
        value = json.loads(payload[:-1].decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CliComparatorError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise CliComparatorError(f"{label} must be a JSON object")
    return value


def _environment_hash(cargo_version: str) -> str:
    value = {
        "cargo_net_offline": True,
        "cargo_version": cargo_version,
        "platform": "windows-x86_64",
        "process_contract": "sipi-cli-single-json-response-v1",
        "runner_environment": "SystemRoot_System32_only",
    }
    return _sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _materialize_cli(product_root: Path, product_commit: str, temp_root: Path) -> tuple[Path, dict[str, object]]:
    archive = subprocess.run(
        ["git", "-C", str(product_root), "archive", "--format=tar", product_commit],
        capture_output=True,
    )
    lock = subprocess.run(
        ["git", "-C", str(product_root), "cat-file", "blob", f"{product_commit}:Cargo.lock"],
        capture_output=True,
    )
    if archive.returncode != 0 or lock.returncode != 0:
        raise CliComparatorError("product commit cannot be cleanly materialized")
    tree = subprocess.run(
        ["git", "-C", str(product_root), "rev-parse", f"{product_commit}^{{tree}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source = temp_root / "product-source"
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as document:
        members = document.getmembers()
        if any(not (member.isfile() or member.isdir()) or not _safe_archive_member(member.name) for member in members):
            raise CliComparatorError("product Git archive contains an unsafe member")
        document.extractall(source, members, filter="data")
    cargo = _cargo_executable()
    target = temp_root / "product-target"
    environment = dict(os.environ)
    environment.update({"CARGO_TARGET_DIR": str(target), "CARGO_INCREMENTAL": "0", "CARGO_NET_OFFLINE": "true"})
    completed = subprocess.run(
        [cargo, "build", "--manifest-path", str(source / "Cargo.toml"), "-p", "sipi-cli", "--bin", "sipi", "--release", "--locked"],
        cwd=source,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    executable = target / "release" / "sipi.exe"
    if completed.returncode != 0 or not executable.is_file():
        raise CliComparatorError("clean sipi-cli build failed")
    return executable, {
        "source_commit": product_commit,
        "source_tree": tree,
        "cargo_lock_sha256": _sha256_bytes(lock.stdout),
        "executable_sha256": _sha256_file(executable),
        "executable_bytes": executable.stat().st_size,
        "cargo_version": subprocess.run([cargo, "--version"], check=True, capture_output=True, text=True).stdout.strip(),
    }


def build_request(source: bytes) -> bytes:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CliComparatorError("selected S2P source is not UTF-8") from error
    request = {
        "schema": REQUEST_SCHEMA,
        "source": {"encoding": "utf-8", "text": text},
    }
    return json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _observer_run(source_root: Path, contract: dict[str, Any]) -> tuple[bytes, float, list[float]]:
    with tempfile.TemporaryDirectory(prefix="sipi-channel-s2p-cli-observer-") as directory:
        custody = Path(directory) / "channel.s2p"
        custody.write_bytes(_git_bytes(source_root, contract["source"]))
        source = custody.read_bytes()
        spectrum = parse_two_port_touchstone_ri(source)
        if (
            len(spectrum.samples) != 201
            or spectrum.frequency_step_hz != 100_000_000.0
            or spectrum.reference_impedance_ohm != 50.0
        ):
            raise CliComparatorError("external spectrum does not match frozen matched v1 structure")
        interval, kernel = observer_kernel(spectrum)
    return source, interval, kernel


def parse_cli_response(payload: bytes, source: bytes, expected_interval: float) -> tuple[dict[str, Any], list[float]]:
    response = _strict_json(payload, "CLI stdout")
    if not _exact(response, {"schema", "protocol", "command", "request_id", "status", "result", "diagnostic_count"}):
        raise CliComparatorError("CLI response envelope shape is invalid")
    if (
        response["schema"] != "sipi.cli.response.v1"
        or response["protocol"] != 1
        or response["command"] != "channel"
        or response["request_id"] is not None
        or response["status"] != "ok"
        or response["diagnostic_count"] != 0
    ):
        raise CliComparatorError("CLI response envelope is not the accepted channel result")
    result = response["result"]
    keys = {
        "schema", "input_byte_length", "input_sha256", "one_sided_sample_count",
        "frequency_step_hz", "reference_impedance_ohms", "kernel_sample_count",
        "sample_interval_seconds", "gain_v_per_v", "evaluation_scope",
        "external_profile_acceptance",
    }
    if not _exact(result, keys):
        raise CliComparatorError("CLI channel result shape is invalid")
    if (
        result["schema"] != RESULT_SCHEMA
        or result["input_byte_length"] != len(source)
        or result["input_sha256"] != _sha256_bytes(source)
        or result["one_sided_sample_count"] != 201
        or result["frequency_step_hz"] != 100_000_000.0
        or result["reference_impedance_ohms"] != 50.0
        or result["kernel_sample_count"] != 400
        or result["sample_interval_seconds"] != expected_interval
        or result["evaluation_scope"] != "matched_s21_periodic_kernel_only"
        or result["external_profile_acceptance"] != "caller_input_unattested"
        or not isinstance(result["gain_v_per_v"], list)
        or len(result["gain_v_per_v"]) != 400
    ):
        raise CliComparatorError("CLI channel result metadata is invalid")
    gain = [_finite(value, "CLI channel gain") for value in result["gain_v_per_v"]]
    return response, gain


def compare(contract_path: Path, source_root: Path, product_root: Path, product_commit: str) -> dict[str, Any]:
    contract = _load(contract_path)
    policy = verify_document(contract, source_root)
    if not policy["valid"] or not policy["acceptance_ready"]:
        raise CliComparatorError("matched acceptance policy is invalid")
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise CliComparatorError("this acceptance gate supports Windows x86_64 only")
    if len(product_commit) != 40 or any(character not in "0123456789abcdef" for character in product_commit):
        raise CliComparatorError("product commit must be a full lowercase SHA-1")

    first_source, first_interval, first_kernel = _observer_run(source_root, contract)
    second_source, second_interval, second_kernel = _observer_run(source_root, contract)
    if (
        first_source != second_source
        or first_interval != second_interval
        or _array_hash(first_kernel) != _array_hash(second_kernel)
    ):
        raise CliComparatorError("oracle_nondeterministic")
    expected_interval = contract["acceptance"]["dft"]["sample_interval_seconds"]
    if first_interval != expected_interval:
        raise CliComparatorError("observer sample interval mismatches the frozen policy")
    request = build_request(first_source)

    with tempfile.TemporaryDirectory(prefix="sipi-channel-s2p-cli-") as directory:
        temporary_root = Path(directory)
        executable, identity = _materialize_cli(product_root, product_commit, temporary_root)
        completed = subprocess.run(
            [str(executable), "channel", "run", "--stdin"],
            cwd=temporary_root,
            env=_scrubbed_environment(temporary_root),
            input=request,
            capture_output=True,
        )
    if completed.returncode != 0 or completed.stderr:
        raise CliComparatorError("product CLI process contract failed")
    response, gain = parse_cli_response(completed.stdout, first_source, expected_interval)
    comparison = _compare(
        first_kernel,
        gain,
        contract["acceptance"]["kernel_compare"]["absolute_tolerance_v_per_v"],
        contract["acceptance"]["kernel_compare"]["relative_tolerance"],
    )
    return {
        "schema": SCHEMA,
        "profile_id": PROFILE_ID,
        "status": "passed" if comparison["passed"] else "rejected",
        "accepted": bool(comparison["passed"]),
        "policy_sha256": _sha256_file(contract_path),
        "source": {key: contract["source"][key] for key in ("canonical_origin", "commit", "tree", "path", "git_blob", "content_sha256", "redistribution")},
        "environment": {"platform": "windows-x86_64", "environment_hash": _environment_hash(str(identity["cargo_version"]))},
        "observer": {
            "implementation": "standard_dft_observer_v1",
            "fresh_runs": 2,
            "kernel_sha256_f64le": _array_hash(first_kernel),
            "fft_length": len(first_kernel),
            "sample_interval_seconds": first_interval,
        },
        "request": {"schema": REQUEST_SCHEMA, "sha256": _sha256_bytes(request), "source_byte_length": len(first_source), "source_sha256": _sha256_bytes(first_source)},
        "product": {
            "source_commit": identity["source_commit"],
            "source_tree": identity["source_tree"],
            "cargo_lock_sha256": identity["cargo_lock_sha256"],
            "cargo_version": identity["cargo_version"],
            "executable": "sipi.exe",
            "executable_sha256": identity["executable_sha256"],
            "executable_bytes": identity["executable_bytes"],
            "cli_kernel_sha256_f64le": _array_hash(gain),
        },
        "response": {
            "schema": RESULT_SCHEMA,
            "stdout_sha256": _sha256_bytes(completed.stdout),
            "command": "channel",
            "status": "ok",
            "diagnostic_count": 0,
            "evaluation_scope": "matched_s21_periodic_kernel_only",
            "external_profile_acceptance": "caller_input_unattested",
        },
        "comparison": {
            **comparison,
            "absolute_tolerance": contract["acceptance"]["kernel_compare"]["absolute_tolerance_v_per_v"],
            "relative_tolerance": contract["acceptance"]["kernel_compare"]["relative_tolerance"],
        },
        "non_claims": [
            "This gate accepts only the selected external S2P text through the bounded CLI path.",
            "Ordinary caller input remains unattested at runtime because the CLI has no external asset identity.",
            "It does not establish general Touchstone, reflection, Link/eye/BER, artifact, or release behavior.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=ROOT / "docs" / "baselines" / "channel-s2p-matched-acceptance.v1.yaml")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--product-root", type=Path, required=True)
    parser.add_argument("--product-commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        report = compare(arguments.contract, arguments.source_root, arguments.product_root, arguments.product_commit)
    except (CliComparatorError, ComparatorError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        report = {"schema": SCHEMA, "profile_id": PROFILE_ID, "status": "rejected", "accepted": False, "blockers": ["cli_external_compare_failed"]}
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": report["status"], "accepted": report["accepted"]}, sort_keys=True))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
