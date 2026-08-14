"""Observe bounded IEEE causality on the selected S4P from a clean archive."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path("crates/sipi-p3c/tests/p3c_sealed_s4p_external_causality_runner.rs")
INVENTORY = (
    Path("Cargo.toml"), Path("Cargo.lock"), Path("crates/sipi-artifacts/src/lib.rs"),
    Path("crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs"),
    Path("crates/sipi-ieee-com-sparam/Cargo.toml"),
    Path("crates/sipi-ieee-com-sparam/NOTICE-IEEE-802-COM.md"),
    Path("crates/sipi-ieee-com-sparam/SOURCE-MAP.md"), Path("crates/sipi-ieee-com-sparam/src/lib.rs"),
    Path("crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs"),
    Path("crates/sipi-ieee-com-sparam/src/s21_to_raw_periodic_v1.rs"),
    Path("crates/sipi-ieee-com-sparam/src/s21_to_causal_v1.rs"),
    Path("crates/sipi-p3c/Cargo.toml"), Path("crates/sipi-p3c/src/lib.rs"), RUNNER,
    Path("crates/sipi-touchstone/src/lib.rs"), Path("crates/sipi-touchstone/src/selected_four_port_v1.rs"),
    Path("crates/sipi-types/src/lib.rs"),
)
SCHEMA = "sipi.p3c.sealed-selected-s4p-causality-observation.v1"
RUNNER_SCHEMA = "sipi.p3c.sealed-selected-s4p-causality-runner.v1"
SOURCE_LENGTH = 1_834_156
SOURCE_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"
HEX = set("0123456789abcdef")


class ObservationError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def external_file(path: Path, kind: str) -> Path:
    path = path.resolve(strict=True)
    if not path.is_file() or path.is_relative_to(ROOT.resolve()):
        raise ObservationError(f"{kind}_must_be_external_regular_file")
    return path


def external_report(path: Path) -> Path:
    parent = path.parent.resolve(strict=True)
    if parent.is_relative_to(ROOT.resolve()):
        raise ObservationError("report_must_be_outside_worktree")
    return parent / path.name


def source_identity(path: Path) -> tuple[int, str]:
    identity = path.stat().st_size, sha256(path)
    if identity != (SOURCE_LENGTH, SOURCE_SHA256):
        raise ObservationError("selected_source_identity_mismatch")
    return identity


def clean_archive(destination: Path) -> tuple[str, dict[str, str]]:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True, encoding="ascii").stdout.strip()
    payload = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        if not archive.getnames() or any(Path(name).is_absolute() or ".." in Path(name).parts for name in archive.getnames()):
            raise ObservationError("clean_archive_path_invalid")
        archive.extractall(destination, filter="data")
    try:
        return commit, {path.as_posix(): sha256(destination / path) for path in INVENTORY}
    except OSError as error:
        raise ObservationError("clean_archive_inventory_missing") from error


def hex_string(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and not (set(value) - HEX)


def parse_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("runner_report_invalid") from error
    required = {"schema", "status", "source_byte_length", "source_sha256", "source_identity_checks", "fresh_runs", "cleanup_status"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema") != RUNNER_SCHEMA or value.get("status") not in {"observed", "rejected"} or value.get("source_byte_length") != SOURCE_LENGTH or value.get("source_sha256") != SOURCE_SHA256 or value.get("source_identity_checks") != "before_stage_after_equal" or value.get("cleanup_status") != "complete" or not isinstance(value.get("fresh_runs"), list) or len(value["fresh_runs"]) != 2:
        raise ObservationError("runner_report_contract_invalid")
    first, second = value["fresh_runs"]
    common = {"manifest_sha256", "record_count", "causality_status"}
    if any(not isinstance(run, dict) or not common <= set(run) or not hex_string(run.get("manifest_sha256"), 64) or not isinstance(run.get("record_count"), int) or isinstance(run.get("record_count"), bool) or run["record_count"] <= 0 for run in (first, second)):
        raise ObservationError("runner_run_shape_invalid")
    if first["manifest_sha256"] == second["manifest_sha256"] or first["record_count"] != second["record_count"] or first["causality_status"] != second["causality_status"]:
        raise ObservationError("fresh_run_consistency_invalid")
    if value["status"] == "observed":
        fields = {"manifest_sha256", "record_count", "causality_status", "uniform_bin_count", "causal_sample_count", "sample_interval_bits", "iteration_count", "final_error_bits", "stop", "causal_response_sha256"}
        if any(set(run) != fields or run["causality_status"] != "admitted" or any(not isinstance(run[key], int) or isinstance(run[key], bool) or run[key] <= 0 for key in ("uniform_bin_count", "causal_sample_count", "iteration_count")) or not hex_string(run["sample_interval_bits"], 16) or not hex_string(run["final_error_bits"], 16) or run["stop"] not in {"relative_error", "successive_error_difference"} or not hex_string(run["causal_response_sha256"], 64) for run in (first, second)):
            raise ObservationError("runner_admitted_shape_invalid")
        if any(first[key] != second[key] for key in fields - {"manifest_sha256"}):
            raise ObservationError("admitted_repeatability_invalid")
    else:
        fields = {"manifest_sha256", "record_count", "causality_status", "stage", "error"}
        if any(set(run) != fields or run["causality_status"] != "rejected" or not isinstance(run["stage"], str) or not run["stage"] or not isinstance(run["error"], str) or not run["error"] for run in (first, second)) or first["stage"] != second["stage"] or first["error"] != second["error"]:
            raise ObservationError("runner_rejected_shape_invalid")
    return value


def observe(source: Path, report: Path, cargo: Path) -> dict[str, Any]:
    source, report, cargo = external_file(source, "source"), external_report(report), external_file(cargo, "cargo")
    before = source_identity(source)
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-causality-") as temporary:
        archive_root = Path(temporary) / "archive"
        archive_root.mkdir()
        commit, inventory = clean_archive(archive_root)
        runner_report = Path(temporary) / "runner.json"
        env = os.environ.copy()
        env.update({"SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE": str(source), "SIPI_P3C_SEALED_S4P_CAUSALITY_RUNNER_REPORT": str(runner_report), "CARGO_TARGET_DIR": str(Path(temporary) / "target"), "CARGO_INCREMENTAL": "0", "CARGO_NET_OFFLINE": "true"})
        outcome = subprocess.run([str(cargo), "test", "-p", "sipi-p3c", "--locked", "--offline", "--test", RUNNER.stem, "--", "--ignored", "--exact", "p3c_sealed_s4p_external_causality_runner_v1"], cwd=archive_root, env=env, capture_output=True, text=False, check=False)
        if outcome.returncode:
            raise ObservationError("clean_archive_runner_failed")
        runner = parse_report(runner_report)
        runner_sha = sha256(runner_report)
    if source_identity(source) != before:
        raise ObservationError("source_changed_during_observation")
    first = runner["fresh_runs"][0]
    summary = {key: first[key] for key in first if key != "manifest_sha256"}
    return {"schema": SCHEMA, "status": runner["status"], "custody": "external_only", "report_path_retained": False, "selected_source": {"byte_length": before[0], "sha256": before[1]}, "clean_archive_commit": commit, "product_source_inventory": inventory, "runner_source_sha256": inventory[RUNNER.as_posix()], "runner_report_sha256": runner_sha, "fresh_custody_runs": 2, "manifest_sha256s": [run["manifest_sha256"] for run in runner["fresh_runs"]], "record_count": first["record_count"], "outcome": summary, "source_identity_checks": "before_stage_after_equal", "cleanup_status": "complete", "non_claims": ["The source, temporary ArtifactRoots, detailed report, and all absolute paths remain outside the worktree.", "This invokes only fixed admission, interpolation, and bounded causality enforcement; it does not admit a causal impulse, delay, passivity, truncation, convolution, waveform, ADS equivalence, or acceptance."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = observe(args.source, args.report, args.cargo)
    except (ObservationError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        result = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    try:
        destination = external_report(args.report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"))
    except (ObservationError, OSError):
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": result["status"]}, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] in {"observed", "rejected"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
