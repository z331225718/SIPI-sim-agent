"""Run the two-fresh external ADS fixed-pulse operator observation."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import run_p3c_external_ads_fixed_pulse_operator as pulse


ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path("crates/sipi-p3c/tests/p3c_external_ads_fixed_pulse_operator_runner.rs")
INVENTORY = (
    Path("Cargo.lock"), Path("Cargo.toml"), Path("rust-toolchain.toml"),
    Path("crates/sipi-artifacts/Cargo.toml"), Path("crates/sipi-artifacts/src/lib.rs"),
    Path("crates/sipi-touchstone/Cargo.toml"), Path("crates/sipi-touchstone/src/selected_four_port_v1.rs"),
    Path("crates/sipi-channel/Cargo.toml"), Path("crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs"),
    Path("crates/sipi-ieee-com-sparam/Cargo.toml"), Path("crates/sipi-ieee-com-sparam/src/lib.rs"),
    Path("crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs"), Path("crates/sipi-ieee-com-sparam/src/s21_to_causal_v1.rs"), Path("crates/sipi-ieee-com-sparam/src/s21_to_truncated_v1.rs"),
    Path("crates/sipi-link/Cargo.toml"), Path("crates/sipi-link/src/lib.rs"),
    Path("crates/sipi-contracts/Cargo.toml"), Path("crates/sipi-contracts/src/lib.rs"),
    Path("crates/sipi-types/Cargo.toml"), Path("crates/sipi-types/src/lib.rs"),
    Path("crates/sipi-p3c/Cargo.toml"), Path("crates/sipi-p3c/src/lib.rs"), RUNNER,
    Path("tools/run_p3c_external_ads_fixed_pulse_operator.py"), Path("tools/observe_p3c_ads_fixed_pulse_operator.py"),
)
SCHEMA = "sipi.p3c.ads-fixed-pulse-operator-observation.v1"
RUNNER_SCHEMA = "sipi.p3c.ads-fixed-pulse-operator-runner.v1"


class ObservationError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def external_file(path: Path, kind: str, *, must_exist: bool) -> Path:
    resolved = path.resolve(strict=must_exist)
    if resolved.is_relative_to(ROOT.resolve()):
        raise ObservationError(f"{kind}_must_be_external")
    return resolved


def clean_archive(destination: Path) -> tuple[str, str, dict[str, str]]:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True, encoding="ascii").stdout.strip()
    tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, check=True, capture_output=True, text=True, encoding="ascii").stdout.strip()
    payload = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        names = archive.getnames()
        if not names or any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
            raise ObservationError("clean_archive_path")
        archive.extractall(destination, filter="data")
    try:
        return commit, tree, {path.as_posix(): sha256(destination / path) for path in INVENTORY}
    except OSError as error:
        raise ObservationError("clean_archive_inventory") from error


def parse_runner(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("runner_report_invalid") from error
    required = {"schema", "status", "sample_interval_bits", "pulse", "fresh_runs", "cleanup_status"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema") != RUNNER_SCHEMA or value.get("status") != "observed" or value.get("sample_interval_bits") != "3d712e0be826d695" or value.get("pulse") != {"start_index": 16353, "end_index_exclusive": 16385, "one_volt_sample_count": 32} or value.get("cleanup_status") != "complete":
        raise ObservationError("runner_report_contract")
    runs = value.get("fresh_runs")
    keys = {"manifest_sha256", "ads_payload_sha256", "record_count", "uniform_bin_count", "causality_iterations", "causality_stop", "retained_taps", "input_sha256", "ads_tx_sha256", "ads_rx_sha256", "product_prefix_sha256", "residual_sha256", "pre_pulse_reference_rms_bits", "pre_pulse_product_rms_bits", "pre_pulse_residual_rms_bits", "post_pulse_reference_rms_bits", "post_pulse_product_rms_bits", "post_pulse_residual_rms_bits", "post_pulse_nrmse_bits", "strict_identity"}
    if not isinstance(runs, list) or len(runs) != 2 or any(not isinstance(run, dict) or set(run) != keys for run in runs):
        raise ObservationError("runner_fresh_shape")
    first, second = runs
    if first["manifest_sha256"] == second["manifest_sha256"] or first["ads_payload_sha256"] != second["ads_payload_sha256"]:
        raise ObservationError("runner_fresh_identity")
    normalized = [{key: value for key, value in run.items() if key != "manifest_sha256"} for run in runs]
    if normalized[0] != normalized[1]:
        raise ObservationError("runner_fresh_repeatability")
    if first["record_count"] != 2002 or first["uniform_bin_count"] != 25601 or first["causality_iterations"] != 32 or first["causality_stop"] != "successive_error_difference" or first["retained_taps"] != 10871 or first["input_sha256"] == "":
        raise ObservationError("runner_fixed_path")
    return value


def observe(source: Path, report: Path, cargo: Path) -> dict[str, Any]:
    source = external_file(source, "source", must_exist=True)
    report = external_file(report, "report", must_exist=False)
    cargo = external_file(cargo, "cargo", must_exist=True)
    if report.exists():
        raise ObservationError("report_must_not_exist")
    before = pulse.source_identity(source)
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-fixed-pulse-observation-") as temporary:
        temporary_path = Path(temporary)
        archive = temporary_path / "archive"; archive.mkdir()
        commit, tree, inventory = clean_archive(archive)
        ads_root = temporary_path / "ads"; ads_root.mkdir()
        first = pulse.materialize_run(source, ads_root / "run-1", invoke_ads=True)
        second = pulse.materialize_run(source, ads_root / "run-2", invoke_ads=True)
        first_payload = ads_root / "run-1" / "canonical_pulse_operator_le_f64.bin"
        second_payload = ads_root / "run-2" / "canonical_pulse_operator_le_f64.bin"
        if first.get("generated", {}).get("netlist_sha256") != second.get("generated", {}).get("netlist_sha256") or first.get("waveform", {}).get("payload_sha256") != second.get("waveform", {}).get("payload_sha256"):
            raise ObservationError("ads_fresh_repeatability")
        runner_report = temporary_path / "runner.json"
        environment = os.environ.copy()
        environment.update({
            "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE": str(source),
            "SIPI_P3C_ADS_FIXED_PULSE_PAYLOAD_ONE": str(first_payload),
            "SIPI_P3C_ADS_FIXED_PULSE_PAYLOAD_TWO": str(second_payload),
            "SIPI_P3C_ADS_FIXED_PULSE_OPERATOR_RUNNER_REPORT": str(runner_report),
            "CARGO_TARGET_DIR": str(temporary_path / "target"), "CARGO_INCREMENTAL": "0", "CARGO_NET_OFFLINE": "true",
        })
        result = subprocess.run([str(cargo), "test", "-p", "sipi-p3c", "--release", "--locked", "--offline", "--test", RUNNER.stem, "--", "--ignored", "--exact", "p3c_external_ads_fixed_pulse_operator_runner_v1"], cwd=archive, env=environment, capture_output=True, text=False, check=False)
        if result.returncode:
            raise ObservationError("clean_archive_runner_failed")
        runner = parse_runner(runner_report)
        runner_sha = sha256(runner_report)
        netlist_sha = first["generated"]["netlist_sha256"]
        ads_payload_sha = first["waveform"]["payload_sha256"]
    if pulse.source_identity(source) != before:
        raise ObservationError("source_changed_during_observation")
    fact = runner["fresh_runs"][0]
    return {
        "schema": SCHEMA, "status": "observed", "custody": "external_only", "report_path_retained": False,
        "clean_archive_commit": commit, "clean_archive_tree": tree, "source_byte_length": before[0], "source_sha256": before[1],
        "ads_netlist_sha256": netlist_sha, "ads_canonical_payload_sha256": ads_payload_sha,
        "runner_source_sha256": inventory[RUNNER.as_posix()], "runner_report_sha256": runner_sha,
        "source_inventory": inventory, "fresh_runs": 2, "source_manifests": [run["manifest_sha256"] for run in runner["fresh_runs"]],
        "record_count": fact["record_count"], "uniform_bin_count": fact["uniform_bin_count"], "causality_iterations": fact["causality_iterations"], "causality_stop": fact["causality_stop"], "retained_taps": fact["retained_taps"],
        "input_sha256": fact["input_sha256"], "ads_tx_sha256": fact["ads_tx_sha256"], "ads_rx_sha256": fact["ads_rx_sha256"], "product_prefix_sha256": fact["product_prefix_sha256"], "residual_sha256": fact["residual_sha256"],
        "pre_pulse_reference_rms_bits": fact["pre_pulse_reference_rms_bits"], "pre_pulse_product_rms_bits": fact["pre_pulse_product_rms_bits"], "pre_pulse_residual_rms_bits": fact["pre_pulse_residual_rms_bits"], "post_pulse_reference_rms_bits": fact["post_pulse_reference_rms_bits"], "post_pulse_product_rms_bits": fact["post_pulse_product_rms_bits"], "post_pulse_residual_rms_bits": fact["post_pulse_residual_rms_bits"], "post_pulse_nrmse_bits": fact["post_pulse_nrmse_bits"], "strict_identity": fact["strict_identity"],
        "cleanup_status": "complete", "non_claims": ["This reports one fixed sampled operator delta only.", "It does not identify ADS internal output-strobe or convolution semantics, change product policy, or accept the PRBS profile."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--cargo", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        value = observe(args.source, args.report, args.cargo)
    except (OSError, ValueError, ObservationError, pulse.FixedPulseError, subprocess.SubprocessError, tarfile.TarError) as error:
        value = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    try:
        report = external_file(args.report, "report", must_exist=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii", newline="\n")
    except (OSError, ObservationError):
        print(json.dumps(value, sort_keys=True, separators=(",", ":"))); return 2
    print(json.dumps({"schema": SCHEMA, "status": value["status"]}, sort_keys=True, separators=(",", ":")))
    return 0 if value["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
