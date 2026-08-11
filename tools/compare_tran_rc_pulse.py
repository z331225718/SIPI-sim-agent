"""Run the external RC/PULSE oracle and compare it with the product harness.

This comparator is an observer-side gate. It materializes the required deck
from a fixed Git object into a fresh temporary directory, never exposes that
deck to the product, and writes only hashes and metrics into its report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verify_tran_rc_pulse_acceptance import _load, verify_document


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.tran.rc-pulse.compare.v1"
HARNESS_SCHEMA = "sipi.tran.rc-pulse-harness.v1"
BUILD_INFO_SCHEMA = "agent-spice.build-info.v1"
EXPECTED_ORACLE_REVISION = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
EXPECTED_TIMES = [0.0, 1.0e-6, 2.0e-6, 3.0e-6]
PROFILE_ID = "tran-rc-pulse-v1"


class ComparatorError(RuntimeError):
    """A fail-closed input, execution, or comparison error."""


@dataclass(frozen=True)
class Samples:
    time: list[float]
    voltage_in: list[float]
    voltage_out: list[float]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _array_hash(values: list[float]) -> str:
    return _sha256_bytes(b"".join(struct.pack("<d", value) for value in values))


def _require_sha256(actual_path: Path, expected: str, label: str) -> dict[str, Any]:
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ComparatorError(f"{label} SHA-256 is malformed")
    if not actual_path.is_file():
        raise ComparatorError(f"{label} executable is unavailable")
    actual = _sha256_file(actual_path)
    if actual != expected:
        raise ComparatorError(f"{label} executable SHA-256 mismatch")
    return {"sha256": actual, "bytes": actual_path.stat().st_size}


def _scrubbed_environment(temp_root: Path) -> dict[str, str]:
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise ComparatorError("SystemRoot is required for the Windows external gate")
    system32 = str(Path(system_root) / "System32")
    return {
        "ComSpec": os.environ.get("ComSpec", str(Path(system32) / "cmd.exe")),
        "LANG": "C",
        "PATH": system32,
        "SystemRoot": system_root,
        "TEMP": str(temp_root),
        "TMP": str(temp_root),
    }


def _run(command: list[str], cwd: Path, environment: dict[str, str], label: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, encoding="utf-8", errors="strict")
    if completed.returncode != 0:
        raise ComparatorError(f"{label} exited with {completed.returncode}")
    return completed


def _git_bytes(source_root: Path, revision: str) -> bytes:
    completed = subprocess.run(["git", "-C", str(source_root), "cat-file", "blob", revision], capture_output=True)
    if completed.returncode != 0:
        raise ComparatorError("external fixture Git object is unavailable")
    return completed.stdout


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ComparatorError(f"{label} must be a finite number")
    return float(value)


def parse_oracle_result(document: object) -> Samples:
    if not isinstance(document, dict) or not isinstance(document.get("points"), list):
        raise ComparatorError("oracle result has no point list")
    points = [point for point in document["points"] if isinstance(point, dict) and point.get("analysis") == "tran"]
    if len(points) != len(EXPECTED_TIMES):
        raise ComparatorError("oracle transient point count mismatches the required grid")
    time: list[float] = []
    voltage_in: list[float] = []
    voltage_out: list[float] = []
    for index, point in enumerate(points):
        values = point.get("values")
        if not isinstance(values, dict) or set(values) & {"in", "out"} != {"in", "out"}:
            raise ComparatorError(f"oracle transient point {index} lacks in/out voltages")
        time.append(_finite_number(point.get("x"), f"oracle time[{index}]"))
        voltage_in.append(_finite_number(values["in"], f"oracle v(in)[{index}]"))
        voltage_out.append(_finite_number(values["out"], f"oracle v(out)[{index}]"))
    _require_expected_grid(time, "oracle")
    return Samples(time, voltage_in, voltage_out)


def parse_product_harness(document: object) -> Samples:
    if not isinstance(document, dict) or set(document) != {"schema", "profileId", "timeSeconds", "voltageInVolts", "voltageOutVolts"}:
        raise ComparatorError("product harness schema is invalid")
    if document["schema"] != HARNESS_SCHEMA or document["profileId"] != PROFILE_ID:
        raise ComparatorError("product harness identity mismatches the required profile")
    arrays = (document["timeSeconds"], document["voltageInVolts"], document["voltageOutVolts"])
    if not all(isinstance(array, list) for array in arrays):
        raise ComparatorError("product harness arrays are invalid")
    time = [_finite_number(value, f"product time[{index}]") for index, value in enumerate(document["timeSeconds"])]
    voltage_in = [_finite_number(value, f"product v(in)[{index}]") for index, value in enumerate(document["voltageInVolts"])]
    voltage_out = [_finite_number(value, f"product v(out)[{index}]") for index, value in enumerate(document["voltageOutVolts"])]
    if len(voltage_in) != len(time) or len(voltage_out) != len(time):
        raise ComparatorError("product harness array lengths mismatch")
    _require_expected_grid(time, "product")
    return Samples(time, voltage_in, voltage_out)


def _require_expected_grid(values: list[float], label: str) -> None:
    if len(values) != len(EXPECTED_TIMES):
        raise ComparatorError(f"{label} time grid length mismatches the required profile")
    for index, (actual, expected) in enumerate(zip(values, EXPECTED_TIMES, strict=True)):
        if abs(actual - expected) > 1.0e-15:
            raise ComparatorError(f"{label} time grid mismatches at index {index}")


def _samples_metadata(samples: Samples) -> dict[str, Any]:
    return {
        "length": len(samples.time),
        "time_sha256_f64le": _array_hash(samples.time),
        "voltage_in_sha256_f64le": _array_hash(samples.voltage_in),
        "voltage_out_sha256_f64le": _array_hash(samples.voltage_out),
    }


def _compare(name: str, expected: list[float], actual: list[float], absolute: float, relative: float) -> dict[str, Any]:
    if len(expected) != len(actual):
        raise ComparatorError(f"{name} arrays have different lengths")
    worst_index = 0
    max_abs = -1.0
    max_rel = 0.0
    allowed_at_worst = 0.0
    passed = True
    for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
        difference = abs(left - right)
        scale = max(abs(left), abs(right))
        threshold = absolute + relative * scale
        if difference > threshold:
            passed = False
        if difference > max_abs:
            max_abs = difference
            worst_index = index
            allowed_at_worst = threshold
        if scale != 0.0:
            max_rel = max(max_rel, difference / scale)
    return {
        "observable": name,
        "passed": passed,
        "absolute_tolerance": absolute,
        "relative_tolerance": relative,
        "max_absolute_error": max_abs,
        "max_relative_error": max_rel,
        "allowed_error_at_worst_index": allowed_at_worst,
        "worst_index": worst_index,
    }


def _oracle_build_info(executable: Path, temp_root: Path) -> dict[str, Any]:
    completed = _run([str(executable), "build-info", "--json"], temp_root, _scrubbed_environment(temp_root), "oracle build-info")
    try:
        build_info = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ComparatorError("oracle build-info is not JSON") from error
    expected = {
        "schema": BUILD_INFO_SCHEMA,
        "crateName": "agent-spice-sim",
        "gitDirty": False,
        "gitRevision": EXPECTED_ORACLE_REVISION,
        "profile": "release",
        "target": "x86_64-pc-windows-msvc",
    }
    if not isinstance(build_info, dict) or any(build_info.get(key) != value for key, value in expected.items()):
        raise ComparatorError("oracle build-info identity mismatch")
    return {key: build_info[key] for key in sorted(expected)}


def _run_oracle(executable: Path, source_root: Path, source: dict[str, Any], temp_root: Path, run_id: str) -> Samples:
    run_root = temp_root / run_id
    run_root.mkdir()
    fixture = _git_bytes(source_root, f"{source['commit']}:{source['path']}")
    if _sha256_bytes(fixture) != source["content_sha256"]:
        raise ComparatorError("materialized external fixture hash mismatches the contract")
    deck = run_root / "rc.cir"
    deck.write_bytes(fixture)
    output = run_root / "result.json"
    log = run_root / "engine.log"
    _run([str(executable), str(deck), "--output-json", str(output), "--log", str(log)], run_root, _scrubbed_environment(temp_root), f"oracle {run_id}")
    if not output.is_file():
        raise ComparatorError(f"oracle {run_id} did not publish JSON")
    try:
        return parse_oracle_result(json.loads(output.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise ComparatorError(f"oracle {run_id} JSON is invalid") from error


def _run_product(executable: Path, temp_root: Path) -> Samples:
    completed = _run([str(executable)], temp_root, _scrubbed_environment(temp_root), "product harness")
    try:
        return parse_product_harness(json.loads(completed.stdout))
    except json.JSONDecodeError as error:
        raise ComparatorError("product harness is not JSON") from error


def compare(
    contract_path: Path,
    source_root: Path,
    oracle_executable: Path,
    oracle_sha256: str,
    product_executable: Path,
    product_sha256: str,
    product_commit: str,
) -> dict[str, Any]:
    contract = _load(contract_path)
    contract_check = verify_document(contract, source_root, require_ready=True)
    if not contract_check["valid"] or not contract_check["acceptance_ready"]:
        raise ComparatorError("acceptance contract is not ready: " + "; ".join(contract_check["blockers"]))
    if len(product_commit) != 40 or any(character not in "0123456789abcdef" for character in product_commit):
        raise ComparatorError("product commit must be a full lowercase SHA-1")
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ComparatorError("this external acceptance gate supports Windows x86_64 only")

    oracle_identity = _require_sha256(oracle_executable, oracle_sha256, "oracle")
    product_identity = _require_sha256(product_executable, product_sha256, "product")
    with tempfile.TemporaryDirectory(prefix="sipi-tran-rc-pulse-") as temp:
        temp_root = Path(temp)
        oracle_identity["build_info"] = _oracle_build_info(oracle_executable, temp_root)
        first = _run_oracle(oracle_executable, source_root, contract["source"], temp_root, "oracle-run-1")
        second = _run_oracle(oracle_executable, source_root, contract["source"], temp_root, "oracle-run-2")
        first_metadata = _samples_metadata(first)
        second_metadata = _samples_metadata(second)
        if first_metadata != second_metadata:
            raise ComparatorError("oracle_nondeterministic")
        product = _run_product(product_executable, temp_root)

    comparisons = [
        _compare("time_axis_seconds", first.time, product.time, 1.0e-15, 0.0),
        _compare("voltage_in_volts", first.voltage_in, product.voltage_in, 1.0e-9, 1.0e-9),
        _compare("voltage_out_volts", first.voltage_out, product.voltage_out, 2.0e-6, 5.0e-4),
    ]
    return {
        "schema": SCHEMA,
        "profile_id": PROFILE_ID,
        "status": "passed" if all(item["passed"] for item in comparisons) else "rejected",
        "accepted": all(item["passed"] for item in comparisons),
        "contract_sha256": _sha256_file(contract_path),
        "source": {key: contract["source"][key] for key in ("canonical_origin", "commit", "tree", "path", "git_blob", "content_sha256", "redistribution")},
        "environment": {"platform": "windows-x86_64", "legacy_and_python_environment": "scrubbed"},
        "oracle": {**oracle_identity, "runs": {"first": first_metadata, "second": second_metadata}},
        "product": {**product_identity, "source_commit": product_commit, "samples": _samples_metadata(product)},
        "comparisons": comparisons,
        "non_claims": [
            "This gate compares only the fixed RC/PULSE profile's indexed time, v(in), and v(out) arrays.",
            "It does not establish netlist parsing, OP, AC, general SPICE, or broader TRAN parity.",
            "The report contains hashes and metrics only; it does not retain fixture or waveform arrays.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=ROOT / "docs" / "baselines" / "tran-rc-pulse-acceptance.v1.yaml")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--oracle-exe", type=Path, required=True)
    parser.add_argument("--oracle-sha256", required=True)
    parser.add_argument("--product-exe", type=Path, required=True)
    parser.add_argument("--product-sha256", required=True)
    parser.add_argument("--product-commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report: dict[str, Any]
    try:
        report = compare(args.contract, args.source_root, args.oracle_exe, args.oracle_sha256, args.product_exe, args.product_sha256, args.product_commit)
    except (ComparatorError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        report = {"schema": SCHEMA, "profile_id": PROFILE_ID, "status": "rejected", "accepted": False, "blockers": [str(error)]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": report["status"], "accepted": report["accepted"]}, sort_keys=True))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
