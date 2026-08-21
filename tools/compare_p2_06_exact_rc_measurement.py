"""Compare one exact deck through both product and pinned Agent-Spice parsers.

The deck is first-party input. The external source stays in external custody;
the report retains only its Git identities plus deterministic result metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from compare_tran_rc_pulse import (
    EXPECTED_ORACLE_REVISION,
    EXPECTED_TIMES,
    Samples,
    _compare,
    _require_expected_grid,
    _run,
    _samples_metadata,
    _scrubbed_environment,
    _sha256_bytes,
    _sha256_file,
    parse_oracle_result,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p2-06.exact-rc-measurement-compare.v1"
HARNESS_SCHEMA = "sipi.tran.exact-rc-measurement-harness.v1"
DECK = (
    b"Agent-Spice bounded RC measurement\n"
    b"V1 in 0 PULSE(0 1 1u 1n 1n 10u 20u)\n"
    b"R1 in out 1k\n"
    b"C1 out 0 1u\n"
    b".tran 1u 3u\n"
    b".measure TRAN vmax MAX V(out)\n"
    b".end\n"
)
SOURCE_OBJECTS = {
    "LICENSE": "55aac2e4f8c36a978d315efb02815972579b8293",
    "LICENSE-MANIFEST.md": "2b549451fdf28b4fbaf524010efbe33c6d49b385",
    "native/agent-spice-sim/Cargo.toml": "b56d29811d0293c878b22485523f03ea06dc2d91",
    "native/agent-spice-sim/src/netlist.rs": "83ffa04c90fb7c523875fb93c64b1f245793bcd1",
    "native/agent-spice-sim/src/simulator.rs": "ed5712567420013d70c39a14257e1f77004a64b4",
    "native/agent-spice-sim/src/result.rs": "f13c37b9fd367c5cb66a148deecedcea7d12b794",
    "native/agent-spice-sim/src/main.rs": "a333857287fc093f2f1fa515b135fe31a2bc9eb1",
}
PRODUCT_SOURCES = (
    "Cargo.lock",
    "crates/sipi-runtime/src/lib.rs",
    "crates/sipi-types/src/lib.rs",
    "crates/sipi-tran/Cargo.toml",
    "crates/sipi-tran/src/lib.rs",
    "crates/sipi-tran/src/parsed_rc_measurement_v1.rs",
    "crates/sipi-tran/examples/exact_rc_measurement_stdin.rs",
)


class CompareError(RuntimeError):
    pass


def parse_product(document: object) -> tuple[Samples, dict[str, Any]]:
    if not isinstance(document, dict) or set(document) != {
        "schema", "timeSeconds", "voltageInVolts", "voltageOutVolts", "measurement",
    }:
        raise CompareError("product_harness_shape_invalid")
    if document["schema"] != HARNESS_SCHEMA:
        raise CompareError("product_harness_schema_invalid")
    arrays = (document["timeSeconds"], document["voltageInVolts"], document["voltageOutVolts"])
    if not all(isinstance(array, list) for array in arrays):
        raise CompareError("product_arrays_invalid")
    converted: list[list[float]] = []
    for array in arrays:
        values = [float(value) for value in array]
        if any(not math.isfinite(value) for value in values):
            raise CompareError("product_nonfinite")
        converted.append(values)
    samples = Samples(*converted)
    if len(samples.time) != len(samples.voltage_in) or len(samples.time) != len(samples.voltage_out):
        raise CompareError("product_array_length_mismatch")
    _require_expected_grid(samples.time, "product")
    measurement = document["measurement"]
    expected_shape = {
        "analysis": "tran", "name": "vmax", "operation": "max", "target": "v(out)"
    }
    if not isinstance(measurement, dict) or any(measurement.get(key) != value for key, value in expected_shape.items()):
        raise CompareError("product_measurement_shape_invalid")
    value = measurement.get("valueVolts")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CompareError("product_measurement_nonfinite")
    return samples, {**expected_shape, "value_volts": float(value)}


def git_identity(source_root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(source_root), *args], capture_output=True, text=True,
            encoding="utf-8", errors="strict", timeout=60,
        )
        if completed.returncode != 0:
            raise CompareError("oracle_git_identity_failed")
        return completed.stdout.strip()

    if git("rev-parse", "HEAD") != EXPECTED_ORACLE_REVISION:
        raise CompareError("oracle_revision_mismatch")
    if git("status", "--porcelain=v1", "--untracked-files=no"):
        raise CompareError("oracle_tracked_worktree_dirty")
    tree = git("rev-parse", f"{EXPECTED_ORACLE_REVISION}^{{tree}}")
    objects = {
        path: git("rev-parse", f"{EXPECTED_ORACLE_REVISION}:{path}")
        for path in SOURCE_OBJECTS
    }
    if objects != SOURCE_OBJECTS:
        raise CompareError("oracle_source_object_mismatch")
    return {"commit": EXPECTED_ORACLE_REVISION, "tree": tree, "objects": objects}


def parse_oracle_measurement(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or not isinstance(document.get("measurements"), list):
        raise CompareError("oracle_measurement_list_missing")
    measurements = document["measurements"]
    if len(measurements) != 1 or not isinstance(measurements[0], dict):
        raise CompareError("oracle_measurement_count_invalid")
    measurement = measurements[0]
    if measurement.get("analysis") != "tran" or measurement.get("name") != "vmax":
        raise CompareError("oracle_measurement_identity_invalid")
    value = measurement.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CompareError("oracle_measurement_value_invalid")
    return {
        "analysis": "tran",
        "name": "vmax",
        "operation": "max",
        "target": "v(out)",
        "value_volts": float(value),
        "source_path": "SimulationResult.measurements[0]",
    }


def run_product(product_exe: Path, cwd: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [str(product_exe)], cwd=cwd, env=environment, input=DECK.decode("ascii"),
        capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=60,
    )
    if completed.returncode != 0:
        raise CompareError(f"product exited with {completed.returncode}")
    return completed


def run_compare(source_root: Path, oracle_exe: Path, product_exe: Path) -> dict[str, Any]:
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise CompareError("unsupported_platform")
    source = git_identity(source_root)
    if not oracle_exe.is_file() or not product_exe.is_file():
        raise CompareError("executable_missing")

    with tempfile.TemporaryDirectory(prefix="sipi-p2-06-exact-compare-") as temp:
        temp_root = Path(temp)
        build_info_run = _run(
            [str(oracle_exe), "build-info", "--json"], temp_root,
            _scrubbed_environment(temp_root), "oracle build-info",
        )
        build_info = json.loads(build_info_run.stdout)
        required_build = {
            "schema": "agent-spice.build-info.v1",
            "crateName": "agent-spice-sim",
            "gitRevision": EXPECTED_ORACLE_REVISION,
            "gitDirty": False,
            "profile": "release",
            "target": "x86_64-pc-windows-msvc",
        }
        if not isinstance(build_info, dict) or any(build_info.get(key) != value for key, value in required_build.items()):
            raise CompareError("oracle_build_identity_mismatch")

        oracle_runs: list[tuple[Samples, dict[str, Any], str]] = []
        for index in (1, 2):
            run_root = temp_root / f"oracle-{index}"
            run_root.mkdir()
            deck = run_root / "rc.cir"
            deck.write_bytes(DECK)
            result = run_root / "result.json"
            _run(
                [str(oracle_exe), str(deck), "--output-json", str(result), "--log", str(run_root / "run.log")],
                run_root, _scrubbed_environment(temp_root), f"oracle {index}",
            )
            result_bytes = result.read_bytes()
            document = json.loads(result_bytes.decode("utf-8"))
            oracle_runs.append((
                parse_oracle_result(document),
                parse_oracle_measurement(document),
                _sha256_bytes(result_bytes),
            ))
        if oracle_runs[0] != oracle_runs[1]:
            raise CompareError("oracle_nondeterministic")

        product_runs: list[tuple[Samples, dict[str, Any]]] = []
        for index in (1, 2):
            run_root = temp_root / f"product-{index}"
            run_root.mkdir()
            completed = run_product(product_exe, run_root, _scrubbed_environment(temp_root))
            product_runs.append(parse_product(json.loads(completed.stdout)))
        if product_runs[0] != product_runs[1]:
            raise CompareError("product_nondeterministic")

    oracle, oracle_measurement, oracle_result_sha256 = oracle_runs[0]
    product, measurement = product_runs[0]
    comparisons = [
        _compare("time_axis_seconds", oracle.time, product.time, 1.0e-15, 0.0),
        _compare("voltage_in_volts", oracle.voltage_in, product.voltage_in, 1.0e-9, 1.0e-9),
        _compare("voltage_out_volts", oracle.voltage_out, product.voltage_out, 2.0e-6, 5.0e-4),
        _compare(
            "measurement_max_v_out_volts",
            [oracle_measurement["value_volts"]],
            [measurement["value_volts"]],
            2.0e-6,
            5.0e-4,
        ),
    ]
    accepted = all(item["passed"] for item in comparisons)
    product_sources = {relative: _sha256_file(ROOT / relative) for relative in PRODUCT_SOURCES}
    return {
        "schema": SCHEMA,
        "status": "accepted" if accepted else "rejected",
        "accepted": accepted,
        "input": {
            "origin": "first_party_exact_profile",
            "bytes": len(DECK),
            "sha256": _sha256_bytes(DECK),
            "same_bytes_supplied_to_oracle_and_product": True,
        },
        "source": {**source, "license": "MIT", "redistribution": "external_only_hash_bound"},
        "oracle": {
            "executable_sha256": _sha256_file(oracle_exe),
            "build_info": {key: build_info[key] for key in sorted(required_build)},
            "runs": 2,
            "samples": _samples_metadata(oracle),
            "result_json_sha256": oracle_result_sha256,
            "measurement": oracle_measurement,
        },
        "product": {
            "executable_sha256": _sha256_file(product_exe),
            "source_sha256": product_sources,
            "runs": 2,
            "samples": _samples_metadata(product),
            "measurement": measurement,
        },
        "comparisons": comparisons,
        "non_claims": [
            "This compares only the exact bounded RC/PULSE transient and its engine-produced MAX V(out).",
            "The product rejects OP, AC, generic devices, and measurement extensions.",
            "The report retains source hashes and metrics, not third-party source bytes or waveform arrays.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--oracle-exe", type=Path, required=True)
    parser.add_argument("--product-exe", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_compare(args.source_root, args.oracle_exe, args.product_exe)
    except (CompareError, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "accepted": False, "blockers": [str(error)]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": report["status"], "accepted": report["accepted"]}, sort_keys=True))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
