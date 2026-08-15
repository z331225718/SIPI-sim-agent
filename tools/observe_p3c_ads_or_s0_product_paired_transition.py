"""Run two fresh exact-axis ADS OR/S0 and product paired-transition observations."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ADS_RUNNER = Path("tools/run_p3c_external_ads_or_s0_paired_transition.py")
EXTRACTOR = Path("tools/extract_p3c_ads_pre_final_common_nodes.py")
RUST_RUNNER = Path("crates/sipi-p3c/tests/p3c_ads_or_s0_product_paired_transition_runner.rs")
OBSERVER = Path("tools/observe_p3c_ads_or_s0_product_paired_transition.py")
SCHEMA = "sipi.p3c.ads-or-s0-product-paired-transition-observation.v1"
SOURCE = (1_834_156, "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47")
HELP = (150_522, "45372e9c7c79492bf6023a4e860f05a20caf0ef5e2a083407c119909afc187bf")
INVENTORY = (ADS_RUNNER, EXTRACTOR, RUST_RUNNER, OBSERVER)
HEX = frozenset("0123456789abcdef")


class ObservationError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def external(path: Path, kind: str, *, exists: bool) -> Path:
    value = path.resolve(strict=exists)
    if value.is_relative_to(ROOT.resolve()):
        raise ObservationError(f"{kind}_must_be_external")
    return value


def identity(path: Path, expected: tuple[int, str], reason: str) -> tuple[int, str]:
    value = path.stat().st_size, sha256(path)
    if value != expected:
        raise ObservationError(reason)
    return value


def cargo() -> Path:
    value = Path.home() / ".cargo" / "bin" / "cargo.exe"
    if not value.is_file():
        raise ObservationError("cargo_unavailable")
    return value


def clean_archive(destination: Path) -> tuple[str, str, dict[str, str]]:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True, encoding="ascii").stdout.strip()
    tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, check=True, capture_output=True, text=True, encoding="ascii").stdout.strip()
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as payload:
        if not payload.getnames() or any(Path(name).is_absolute() or ".." in Path(name).parts for name in payload.getnames()):
            raise ObservationError("archive_path")
        payload.extractall(destination, filter="data")
    return commit, tree, {path.as_posix(): sha256(destination / path) for path in INVENTORY}


def hex_value(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and set(value) <= HEX


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("ads_manifest_invalid") from error
    paired = value.get("or_s0_paired_hdiff") if isinstance(value, dict) else None
    required = {"payload", "common_node_count", "mapping", "axis_sha256", "original_hdiff_sha256", "s0_hdiff_sha256", "documented_surface_transition"}
    if not isinstance(value, dict) or value.get("runtime_invoked") is not True or value.get("source") != {"byte_length": SOURCE[0], "sha256": SOURCE[1]} or not isinstance(paired, dict) or set(paired) != required:
        raise ObservationError("ads_manifest_shape")
    payload = paired["payload"]
    if paired["common_node_count"] != 1024 or paired["mapping"] != "or_index_equals_4_times_s0_index" or not isinstance(payload, dict) or set(payload) != {"byte_length", "sha256"} or not isinstance(payload["byte_length"], int) or payload["byte_length"] <= 0 or not hex_value(payload["sha256"]):
        raise ObservationError("ads_manifest_pair")
    if not all(hex_value(paired[key]) for key in ("axis_sha256", "original_hdiff_sha256", "s0_hdiff_sha256")):
        raise ObservationError("ads_manifest_digest")
    return value


def read_product(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("product_report_invalid") from error
    required = {"schema", "status", "manifest_sha256", "record_count", "common_node_count", "sample_interval_bits", "raw_sample_count", "bounded_sample_count", "causality_iterations", "causality_stop", "ads_payload_byte_length", "ads_payload_sha256", "axis_sha256", "ads_original_sha256", "ads_s0_sha256", "product_raw_sha256", "product_bounded_sha256", "ads_transition_sha256", "product_transition_sha256", "paired_delta_sha256", "paired_delta_l2_squared_bits", "paired_delta_max_abs_bits", "paired_delta_max_index", "cleanup_status"}
    if not isinstance(value, dict) or set(value) != required or value["schema"] != "sipi.p3c.ads-or-s0-product-paired-transition-runner.v1" or value["status"] != "observed" or value["record_count"] != 2002 or value["common_node_count"] != 1024 or value["sample_interval_bits"] != "3d712e0be826d695" or value["raw_sample_count"] != 51_200 or value["bounded_sample_count"] != 51_200 or value["causality_iterations"] != 32 or value["causality_stop"] != "successive_error_difference" or value["cleanup_status"] != "complete":
        raise ObservationError("product_report_shape")
    if not isinstance(value["ads_payload_byte_length"], int) or value["ads_payload_byte_length"] <= 0 or not isinstance(value["paired_delta_max_index"], int) or not 0 <= value["paired_delta_max_index"] < 1024:
        raise ObservationError("product_report_count")
    for key in ("manifest_sha256", "ads_payload_sha256", "axis_sha256", "ads_original_sha256", "ads_s0_sha256", "product_raw_sha256", "product_bounded_sha256", "ads_transition_sha256", "product_transition_sha256", "paired_delta_sha256"):
        if not hex_value(value[key]):
            raise ObservationError("product_report_digest")
    if not hex_value(value["paired_delta_l2_squared_bits"], 16) or not hex_value(value["paired_delta_max_abs_bits"], 16):
        raise ObservationError("product_report_bits")
    return value


def observe(source: Path, help_file: Path, report: Path) -> dict[str, Any]:
    source = external(source, "source", exists=True); help_file = external(help_file, "ads_help", exists=True); report = external(report, "report", exists=False)
    if report.exists() or help_file.name != "Transient_Simulation_Parameters.html":
        raise ObservationError("report_or_help_invalid")
    source_before = identity(source, SOURCE, "source_identity"); help_before = identity(help_file, HELP, "help_identity")
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-or-s0-paired-") as temporary:
        root = Path(temporary); archive = root / "archive"; archive.mkdir(); commit, tree, inventory = clean_archive(archive)
        ads_root = root / "ads"; ads_root.mkdir(); target = root / "target"; runs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for run_id in ("run-1", "run-2"):
            ads = subprocess.run([sys.executable, "-B", str(archive / ADS_RUNNER), "--s4p", str(source), "--output-root", str(ads_root), "--run-id", run_id, "--run"], cwd=archive, check=False, capture_output=True, text=True, encoding="utf-8", errors="strict")
            if ads.returncode:
                raise ObservationError("ads_run_rejected")
            manifest = read_manifest(ads_root / run_id / "manifest.json"); payload = ads_root / run_id / "or-s0-hdiff.bin"; paired = manifest["or_s0_paired_hdiff"]
            identity(payload, (paired["payload"]["byte_length"], paired["payload"]["sha256"]), "payload_identity")
            output = root / f"product-{run_id}.json"; environment = os.environ.copy(); environment.update({"SIPI_P3C_SOURCE": str(source), "SIPI_P3C_ADS_OR_S0_HDIFF_PAYLOAD": str(payload), "SIPI_P3C_REPORT": str(output), "SIPI_P3C_RUN_ID": run_id, "CARGO_TARGET_DIR": str(target), "CARGO_INCREMENTAL": "0"})
            product = subprocess.run([str(cargo()), "test", "--release", "--locked", "--offline", "-p", "sipi-p3c", "--test", RUST_RUNNER.stem, "--", "--ignored", "--exact", "p3c_ads_or_s0_product_paired_transition_runner_v1"], cwd=archive, env=environment, check=False, capture_output=True, text=True, encoding="utf-8", errors="strict")
            if product.returncode:
                raise ObservationError("product_transition_rejected")
            fact = read_product(output)
            if fact["ads_payload_byte_length"] != paired["payload"]["byte_length"] or fact["ads_payload_sha256"] != paired["payload"]["sha256"] or fact["axis_sha256"] != paired["axis_sha256"]:
                raise ObservationError("ads_product_binding")
            runs.append((manifest, fact))
        first, second = dict(runs[0][1]), dict(runs[1][1]); first.pop("manifest_sha256"); second.pop("manifest_sha256")
        if runs[0][0]["generated"] != runs[1][0]["generated"] or runs[0][0]["or_s0_paired_hdiff"] != runs[1][0]["or_s0_paired_hdiff"] or first != second or runs[0][1]["manifest_sha256"] == runs[1][1]["manifest_sha256"]:
            raise ObservationError("fresh_drift")
    if identity(source, SOURCE, "source_changed") != source_before or identity(help_file, HELP, "help_changed") != help_before:
        raise ObservationError("external_identity_changed")
    manifest, fact = runs[0]
    return {"schema": SCHEMA, "status": "observed", "custody": "external_only", "report_path_retained": False, "clean_archive_commit": commit, "clean_archive_tree": tree, "source_byte_length": source_before[0], "source_sha256": source_before[1], "ads_help_byte_length": help_before[0], "ads_help_sha256": help_before[1], "fresh_runs": 2, "tool_inventory": {"ads_runner": inventory[ADS_RUNNER.as_posix()], "extractor": inventory[EXTRACTOR.as_posix()], "product_runner": inventory[RUST_RUNNER.as_posix()], "observer": inventory[OBSERVER.as_posix()]}, "ads_netlist": manifest["generated"], "ads_or_s0": manifest["or_s0_paired_hdiff"], "paired_transition": {key: fact[key] for key in fact if key not in {"schema", "status", "manifest_sha256", "ads_payload_byte_length", "ads_payload_sha256", "cleanup_status"}}, "cleanup_status": "complete", "non_claims": ["This compares exact common-node documented ADS surfaces with product raw and bounded responses only.", "It does not identify ADS algorithm, causality, interpolation, passivity, or waveform mismatch cause."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--source", type=Path, required=True); parser.add_argument("--ads-help", type=Path, required=True); parser.add_argument("--report", type=Path, required=True); args = parser.parse_args()
    try:
        value = observe(args.source, args.ads_help, args.report)
    except (OSError, ValueError, ObservationError, subprocess.SubprocessError, tarfile.TarError) as error:
        value = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii", newline="\n")
    print(json.dumps({"schema": SCHEMA, "status": value["status"]}, sort_keys=True)); return 0 if value["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
