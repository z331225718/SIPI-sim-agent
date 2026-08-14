"""Run a two-fresh, hash-only ADS passivity action-surface observation."""

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
RUNNER = Path("tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py")
PREDECESSOR = Path("tools/run_p3c_external_ads_fixed_pulse_operator.py")
SCHEMA = "sipi.p3c.ads-fixed-pulse-passivity-surface-observation.v1"
HELP_EXPECTED = "Transient_Simulation_Parameters.html"
EXPECTED_SURFACE = {
    "vectorset_count": 65,
    "s0_vectorset_count": 16,
    "vectorset_identity_sha256": "d8a2e18a8237e81b7f0ce559b26116bae2aa82b5672a54e81a948bb8c07b3087",
}
INVENTORY = (RUNNER, PREDECESSOR, Path("tools/observe_p3c_ads_fixed_pulse_passivity_surface.py"))


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
    value = path.stat().st_size, sha256(path)
    expected = (1_834_156, "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47")
    if value != expected:
        raise ObservationError("selected_s4p_identity_mismatch")
    return value


def help_identity(path: Path) -> tuple[int, str]:
    if path.name != HELP_EXPECTED:
        raise ObservationError("ads_help_allowlist_mismatch")
    return path.stat().st_size, sha256(path)


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


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("ads_manifest_invalid") from error
    expected = {"schema", "runtime_invoked", "source", "generated", "passivity_surface"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ObservationError("ads_manifest_shape")
    if value["schema"] != "sipi.p3c-external-ads-fixed-pulse-passivity-surface-probe.v1" or value["runtime_invoked"] is not True:
        raise ObservationError("ads_manifest_contract")
    if value["source"] != {"byte_length": 1_834_156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"}:
        raise ObservationError("ads_manifest_source")
    if value["passivity_surface"] != EXPECTED_SURFACE:
        raise ObservationError("ads_passivity_surface_not_observed")
    generated = value["generated"]
    if not isinstance(generated, dict) or set(generated) != {"netlist_sha256", "netlist_byte_length"} or not isinstance(generated["netlist_sha256"], str) or generated["netlist_byte_length"] <= 0:
        raise ObservationError("ads_manifest_generated")
    return value


def observe(source: Path, help_file: Path, report: Path) -> dict[str, Any]:
    source = external_file(source, "source", must_exist=True)
    help_file = external_file(help_file, "ads_help", must_exist=True)
    report = external_file(report, "report", must_exist=False)
    if report.exists():
        raise ObservationError("report_must_not_exist")
    source_before = source_identity(source)
    help_before = help_identity(help_file)
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-passivity-surface-observation-") as temporary:
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
    if source_identity(source) != source_before:
        raise ObservationError("source_changed_during_observation")
    if help_identity(help_file) != help_before:
        raise ObservationError("ads_help_changed_during_observation")
    return {
        "schema": SCHEMA,
        "status": "observed",
        "custody": "external_only",
        "report_path_retained": False,
        "clean_archive_commit": commit,
        "clean_archive_tree": tree,
        "source_byte_length": source_before[0],
        "source_sha256": source_before[1],
        "ads_help_byte_length": help_before[0],
        "ads_help_sha256": help_before[1],
        "runner_source_sha256": inventory[RUNNER.as_posix()],
        "observer_source_sha256": inventory[Path("tools/observe_p3c_ads_fixed_pulse_passivity_surface.py").as_posix()],
        "predecessor_runner_sha256": inventory[PREDECESSOR.as_posix()],
        "fresh_runs": 2,
        "ads_netlist_sha256": manifests[0]["generated"]["netlist_sha256"],
        "ads_netlist_byte_length": manifests[0]["generated"]["netlist_byte_length"],
        "passivity_surface": EXPECTED_SURFACE,
        "cleanup_status": "complete",
        "non_claims": [
            "The documented pre-correction spectrum surface is observable, but correction magnitude is not evaluated.",
            "This does not identify a waveform mismatch cause or change any product policy.",
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
    return 0 if value["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
