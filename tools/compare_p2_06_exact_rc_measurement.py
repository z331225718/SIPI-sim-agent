"""Compare the exact parsed RC/measurement consumer with pinned Agent-Spice."""

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
    _git_bytes,
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
FIXTURE_PATH = "native/AgentSpice.Engine/fixtures/rc.cir"
FIXTURE_BLOB = "f9c29055902fe8aa2b268b4375a5bdbbf67df9da"
FIXTURE_SHA256 = "bcdbd81a40dde01f0e72a8c36be928b6a7325fabbc25f83f72073757154dcefc"
PRODUCT_SOURCES = (
    "Cargo.lock",
    "crates/sipi-runtime/src/lib.rs",
    "crates/sipi-types/src/lib.rs",
    "crates/sipi-tran/Cargo.toml",
    "crates/sipi-tran/src/lib.rs",
    "crates/sipi-tran/src/parsed_rc_measurement_v1.rs",
    "crates/sipi-tran/src/bin/sipi_tran_exact_rc_measurement_harness.rs",
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


def git_identity(source_root: Path) -> dict[str, str]:
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
    blob = git("rev-parse", f"{EXPECTED_ORACLE_REVISION}:{FIXTURE_PATH}")
    if blob != FIXTURE_BLOB:
        raise CompareError("oracle_fixture_blob_mismatch")
    return {"commit": EXPECTED_ORACLE_REVISION, "tree": tree, "path": FIXTURE_PATH, "git_blob": blob}


def run_compare(source_root: Path, oracle_exe: Path, product_exe: Path) -> dict[str, Any]:
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise CompareError("unsupported_platform")
    source = git_identity(source_root)
    fixture = _git_bytes(source_root, f"{EXPECTED_ORACLE_REVISION}:{FIXTURE_PATH}")
    if _sha256_bytes(fixture) != FIXTURE_SHA256:
        raise CompareError("oracle_fixture_content_mismatch")
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

        oracle_runs: list[Samples] = []
        for index in (1, 2):
            run_root = temp_root / f"oracle-{index}"
            run_root.mkdir()
            deck = run_root / "rc.cir"
            deck.write_bytes(fixture)
            result = run_root / "result.json"
            _run(
                [str(oracle_exe), str(deck), "--output-json", str(result), "--log", str(run_root / "run.log")],
                run_root, _scrubbed_environment(temp_root), f"oracle {index}",
            )
            oracle_runs.append(parse_oracle_result(json.loads(result.read_text(encoding="utf-8"))))
        if _samples_metadata(oracle_runs[0]) != _samples_metadata(oracle_runs[1]):
            raise CompareError("oracle_nondeterministic")

        product_runs: list[tuple[Samples, dict[str, Any]]] = []
        for index in (1, 2):
            completed = _run(
                [str(product_exe)], temp_root, _scrubbed_environment(temp_root), f"product {index}"
            )
            product_runs.append(parse_product(json.loads(completed.stdout)))
        if product_runs[0] != product_runs[1]:
            raise CompareError("product_nondeterministic")

    oracle = oracle_runs[0]
    product, measurement = product_runs[0]
    oracle_max = max(oracle.voltage_out)
    comparisons = [
        _compare("time_axis_seconds", oracle.time, product.time, 1.0e-15, 0.0),
        _compare("voltage_in_volts", oracle.voltage_in, product.voltage_in, 1.0e-9, 1.0e-9),
        _compare("voltage_out_volts", oracle.voltage_out, product.voltage_out, 2.0e-6, 5.0e-4),
        _compare("max_v_out_volts", [oracle_max], [measurement["value_volts"]], 2.0e-6, 5.0e-4),
    ]
    accepted = all(item["passed"] for item in comparisons)
    product_sources = {relative: _sha256_file(ROOT / relative) for relative in PRODUCT_SOURCES}
    return {
        "schema": SCHEMA,
        "status": "accepted" if accepted else "rejected",
        "accepted": accepted,
        "source": {**source, "content_sha256": FIXTURE_SHA256, "redistribution": "external_only"},
        "oracle": {
            "executable_sha256": _sha256_file(oracle_exe),
            "build_info": {key: build_info[key] for key in sorted(required_build)},
            "runs": 2,
            "samples": _samples_metadata(oracle),
            "max_v_out_volts": oracle_max,
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
            "This compares only the exact bounded RC/PULSE transient and sampled MAX V(out).",
            "The product rejects OP, AC, generic devices, and measurement extensions.",
            "The report retains hashes and metrics, not external fixture or waveform arrays.",
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
