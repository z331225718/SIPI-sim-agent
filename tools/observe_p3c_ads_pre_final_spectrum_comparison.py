"""Create hash-only two-fresh evidence for strict ADS spectrum-grid comparison."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path("tools/run_p3c_external_ads_fixed_pulse_pre_final_spectrum.py")
PREDECESSOR = Path("tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py")
SCHEMA = "sipi.p3c.ads-pre-final-spectrum-comparison-observation.v1"
HELP_EXPECTED = "Transient_Simulation_Parameters.html"
HELP_IDENTITY = (150_522, "45372e9c7c79492bf6023a4e860f05a20caf0ef5e2a083407c119909afc187bf")
SOURCE_IDENTITY = (1_834_156, "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47")
INVENTORY = (RUNNER, PREDECESSOR, Path("tools/observe_p3c_ads_pre_final_spectrum_comparison.py"))


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


def source_identity(path: Path) -> tuple[int, str]:
    identity = path.stat().st_size, sha256(path)
    if identity != SOURCE_IDENTITY:
        raise ObservationError("selected_s4p_identity_mismatch")
    return identity


def help_identity(path: Path) -> tuple[int, str]:
    if path.name != HELP_EXPECTED:
        raise ObservationError("ads_help_allowlist_mismatch")
    identity = path.stat().st_size, sha256(path)
    if identity != HELP_IDENTITY:
        raise ObservationError("ads_help_identity_mismatch")
    return identity


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


def _axis_summary(value: object) -> dict[str, object]:
    keys = {"point_count", "first_frequency_bits", "last_frequency_bits", "first_step_bits", "axis_sha256"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ObservationError("axis_summary_shape")
    if not isinstance(value["point_count"], int) or value["point_count"] < 2:
        raise ObservationError("axis_summary_count")
    if any(not isinstance(value[key], str) or len(value[key]) != 16 for key in ("first_frequency_bits", "last_frequency_bits", "first_step_bits")):
        raise ObservationError("axis_summary_bits")
    if not isinstance(value["axis_sha256"], str) or len(value["axis_sha256"]) != 64:
        raise ObservationError("axis_summary_digest")
    return value


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("ads_manifest_invalid") from error
    expected = {"schema", "runtime_invoked", "source", "generated", "passivity_surface", "pre_final_axis_comparison"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ObservationError("ads_manifest_shape")
    if value["schema"] != "sipi.p3c-external-ads-fixed-pulse-passivity-surface-probe.v1" or value["runtime_invoked"] is not True:
        raise ObservationError("ads_manifest_contract")
    if value["source"] != {"byte_length": SOURCE_IDENTITY[0], "sha256": SOURCE_IDENTITY[1]}:
        raise ObservationError("ads_manifest_source")
    if value["passivity_surface"] != {"vectorset_count": 65, "s0_vectorset_count": 16, "vectorset_identity_sha256": "d8a2e18a8237e81b7f0ce559b26116bae2aa82b5672a54e81a948bb8c07b3087"}:
        raise ObservationError("ads_manifest_surface")
    generated = value["generated"]
    if not isinstance(generated, dict) or set(generated) != {"netlist_sha256", "netlist_byte_length"}:
        raise ObservationError("ads_manifest_generated")
    comparison = value["pre_final_axis_comparison"]
    required = {"matrix_dimension", "members_per_surface", "s0", "fft_imp", "outcome"}
    if not isinstance(comparison, dict) or set(comparison) != required:
        raise ObservationError("comparison_shape")
    if comparison["matrix_dimension"] != 4 or comparison["members_per_surface"] != 16:
        raise ObservationError("comparison_matrix")
    _axis_summary(comparison["s0"])
    _axis_summary(comparison["fft_imp"])
    if comparison["outcome"] not in {"pre_final_axis_not_identical", "pre_final_axis_identical_payload_delta_not_in_scope"}:
        raise ObservationError("comparison_outcome")
    return value


def observe(source: Path, help_file: Path, report: Path) -> dict[str, Any]:
    source = external_file(source, "source", must_exist=True)
    help_file = external_file(help_file, "ads_help", must_exist=True)
    report = external_file(report, "report", must_exist=False)
    if report.exists():
        raise ObservationError("report_must_not_exist")
    source_before = source_identity(source)
    help_before = help_identity(help_file)
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-pre-final-spectrum-observation-") as temporary:
        temporary_path = Path(temporary)
        archive = temporary_path / "archive"
        archive.mkdir()
        commit, tree, inventory = clean_archive(archive)
        ads_root = temporary_path / "ads"
        ads_root.mkdir()
        manifests: list[dict[str, Any]] = []
        for run_id in ("run-1", "run-2"):
            result = subprocess.run(
                [sys.executable, "-B", str(archive / RUNNER), "--s4p", str(source), "--output-root", str(ads_root), "--run-id", run_id, "--run"],
                cwd=archive,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
            )
            if result.returncode:
                raise ObservationError("clean_archive_ads_probe_failed")
            manifests.append(read_manifest(ads_root / run_id / "manifest.json"))
        if manifests[0]["generated"] != manifests[1]["generated"]:
            raise ObservationError("ads_fresh_netlist_drift")
        if manifests[0]["pre_final_axis_comparison"] != manifests[1]["pre_final_axis_comparison"]:
            raise ObservationError("pre_final_axis_observation_drift")
    if source_identity(source) != source_before:
        raise ObservationError("source_changed_during_observation")
    if help_identity(help_file) != help_before:
        raise ObservationError("ads_help_changed_during_observation")
    comparison = manifests[0]["pre_final_axis_comparison"]
    return {
        "schema": SCHEMA,
        "status": comparison["outcome"],
        "custody": "external_only",
        "report_path_retained": False,
        "clean_archive_commit": commit,
        "clean_archive_tree": tree,
        "source_byte_length": source_before[0],
        "source_sha256": source_before[1],
        "ads_help_byte_length": help_before[0],
        "ads_help_sha256": help_before[1],
        "runner_source_sha256": inventory[RUNNER.as_posix()],
        "observer_source_sha256": inventory[Path("tools/observe_p3c_ads_pre_final_spectrum_comparison.py").as_posix()],
        "predecessor_runner_sha256": inventory[PREDECESSOR.as_posix()],
        "fresh_runs": 2,
        "ads_netlist_sha256": manifests[0]["generated"]["netlist_sha256"],
        "ads_netlist_byte_length": manifests[0]["generated"]["netlist_byte_length"],
        "pre_final_axis_comparison": comparison,
        "cleanup_status": "complete",
        "non_claims": [
            "Only axis layout was retained; no spectrum payload values or paths are retained.",
            "This does not quantify an ADS passivity correction or alter product policy.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--ads-help", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        value = observe(args.source, args.ads_help, args.report)
    except (OSError, ValueError, ObservationError, subprocess.SubprocessError, tarfile.TarError) as error:
        value = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    try:
        report = external_file(args.report, "report", must_exist=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii", newline="\n")
    except (OSError, ObservationError):
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": value["status"]}, sort_keys=True, separators=(",", ":")))
    return 0 if value["status"] != "rejected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
