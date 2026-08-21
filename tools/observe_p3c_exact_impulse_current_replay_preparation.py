"""Prepare the two-fresh P3C current impulse replay without launching ADS."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "805ebb6bbaf588dec08685be4eb78a8ce2fff563"
BASELINE_TREE = "5a378052ea8fdadb8754f22d0a0150088cec6332"
RUNNER_RELATIVE_PATH = Path(
    "crates/sipi-p3c/tests/p3c_external_ads_selected_highloss_waveform_only_runner.rs"
)
RUNNER_TEST = "p3c_external_ads_selected_highloss_waveform_only_runner_v2"
RUNNER_TEST_TARGET = "p3c_external_ads_selected_highloss_waveform_only_runner"
CHILD_SCHEMA = "sipi.p3c.external-ads-selected-highloss-waveform-only-v2-runner.v1"
SUMMARY_SCHEMA = "sipi.p3c.exact-impulse-current-replay-preparation.v1"
S4P_BYTES = 1_834_156
S4P_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"
ADS_BYTES = 1_177_344
ADS_SHA256 = "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726"
CONTRACT_SHA256 = "db0d9a663b311105be329d79060f05a5179f40fd7eccf448faf85d45b73da64a"


class FreshReplayError(ValueError):
    """An external replay preparation precondition failed."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_external(path: Path, *, kind: str, exists: bool = True) -> Path:
    resolved = path.resolve(strict=exists)
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise FreshReplayError(f"{kind}_must_be_external")


def clean_archive_tree(commit: str) -> str:
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise FreshReplayError("clean_archive_commit_invalid")
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", f"{commit}^{{tree}}"],
            check=True,
            capture_output=True,
            text=True,
            encoding="ascii",
        )
    except subprocess.CalledProcessError as error:
        raise FreshReplayError("clean_archive_commit_missing") from error
    tree = result.stdout.strip()
    if tree != BASELINE_TREE:
        raise FreshReplayError("clean_archive_tree_not_fixed")
    return tree


def safe_extract(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, mode="r:") as archive:
        members = archive.getmembers()
        for member in members:
            name = Path(member.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or member.issym()
                or member.islnk()
                or not (member.isdir() or member.isfile())
            ):
                raise FreshReplayError("clean_archive_member_rejected")
        archive.extractall(destination, members=members)


def materialize_clean_archive(commit: str, destination: Path) -> None:
    archive_path = destination.with_suffix(".tar")
    try:
        with archive_path.open("wb") as stream:
            subprocess.run(
                ["git", "-C", str(ROOT), "archive", "--format=tar", commit],
                check=True,
                stdout=stream,
                stderr=subprocess.PIPE,
            )
    except subprocess.CalledProcessError as error:
        raise FreshReplayError("clean_archive_create_failed") from error
    destination.mkdir()
    safe_extract(archive_path, destination)


def _hex(value: object, length: int = 64) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _run_keys() -> set[str]:
    return {
        "source_manifest_sha256",
        "reference_manifest_sha256",
        "candidate_manifest_sha256",
        "record_count",
        "candidate_prefix_sha256",
        "reference_rx_payload_sha256",
        "candidate_payload_sha256",
        "reference_waveform_digest",
        "candidate_waveform_digest",
        "waveform_nrmse_bits",
        "waveform_nrmse_limit_bits",
        "within_waveform_nrmse_limit",
        "within_selected_waveform_only_profile",
    }


def _without_manifests(run: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in run.items()
        if key
        not in {
            "source_manifest_sha256",
            "reference_manifest_sha256",
            "candidate_manifest_sha256",
        }
    }


def assert_child_report(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "status",
        "source_byte_length",
        "source_sha256",
        "ads_canonical_triple_payload_sha256",
        "contract_sha256",
        "source_reference_identity_checks",
        "fresh_runs",
        "cleanup_status",
    }:
        raise FreshReplayError("child_report_shape")
    if value["schema"] != CHILD_SCHEMA or value["status"] != "observed_not_accepted":
        raise FreshReplayError("strict_index_waveform_only_unexpected_acceptance")
    if value["source_byte_length"] != S4P_BYTES or value["source_sha256"] != S4P_SHA256:
        raise FreshReplayError("source_identity:child_report_mismatch")
    if (
        value["ads_canonical_triple_payload_sha256"] != ADS_SHA256
        or value["contract_sha256"] != CONTRACT_SHA256
    ):
        raise FreshReplayError("reference_identity:child_report_mismatch")
    if value["source_reference_identity_checks"] != "before_stage_after_equal":
        raise FreshReplayError("custody_identity_checks")
    if value["cleanup_status"] != "complete":
        raise FreshReplayError("cleanup:child_report_incomplete")
    runs = value["fresh_runs"]
    if not isinstance(runs, list) or len(runs) != 2 or any(not isinstance(run, dict) for run in runs):
        raise FreshReplayError("custody:fresh_runs_invalid")
    first, second = runs
    if set(first) != _run_keys() or set(second) != _run_keys():
        raise FreshReplayError("custody:run_fact_shape")
    for run in runs:
        if (
            not _hex(run["source_manifest_sha256"])
            or not _hex(run["reference_manifest_sha256"])
            or not _hex(run["candidate_manifest_sha256"])
            or not _hex(run["candidate_prefix_sha256"])
            or not _hex(run["reference_rx_payload_sha256"])
            or not _hex(run["candidate_payload_sha256"])
            or not _hex(run["reference_waveform_digest"])
            or not _hex(run["candidate_waveform_digest"])
            or not _hex(run["waveform_nrmse_bits"], 16)
            or not _hex(run["waveform_nrmse_limit_bits"], 16)
            or run["record_count"] != 2002
            or run["within_waveform_nrmse_limit"] is not False
            or run["within_selected_waveform_only_profile"] is not False
        ):
            raise FreshReplayError("strict_index_waveform_only_compare_fact")
    if first["source_manifest_sha256"] == second["source_manifest_sha256"]:
        raise FreshReplayError("custody:source_manifest_not_distinct")
    if first["reference_manifest_sha256"] == second["reference_manifest_sha256"]:
        raise FreshReplayError("custody:reference_manifest_not_distinct")
    if first["candidate_manifest_sha256"] == second["candidate_manifest_sha256"]:
        raise FreshReplayError("custody:candidate_manifest_not_distinct")
    if _without_manifests(first) != _without_manifests(second):
        raise FreshReplayError("custody:canonical_facts_not_equal")
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if any(token in serialized for token in ("file://", "http://", "https://", "C:/", "C:\\", "samples:[", "waveform:[")):
        raise FreshReplayError("report_path_or_payload_leak")
    return value


def _run_child(archive: Path, source: Path, reference: Path, cli: Path, report: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE": str(source),
            "SIPI_P3C_ADS_REFERENCE_CANONICAL_PAYLOAD": str(reference),
            "SIPI_P3C_SELECTED_HIGHLOSS_WAVEFORM_ONLY_CLI": str(cli),
            "SIPI_P3C_SELECTED_HIGHLOSS_WAVEFORM_ONLY_V2_REPORT": str(report),
        }
    )
    command = [
        "cargo",
        "test",
        "--locked",
        "--offline",
        "-p",
        "sipi-p3c",
        "--test",
        RUNNER_TEST_TARGET,
        "--",
        "--ignored",
        RUNNER_TEST,
    ]
    result = subprocess.run(
        command,
        cwd=archive,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise FreshReplayError("external_runner:child_runner_rejected")
    if not report.is_file():
        raise FreshReplayError("report:child_report_missing")


def observe_fresh(*, commit: str, source: Path, reference: Path, cli: Path) -> dict[str, object]:
    if commit != BASELINE_COMMIT:
        raise FreshReplayError("clean_archive_commit_not_fixed")
    tree = clean_archive_tree(commit)
    selected_s4p = require_external(source, kind="s4p")
    ads_reference = require_external(reference, kind="ads_reference")
    product_cli = require_external(cli, kind="product_cli")
    if selected_s4p.stat().st_size != S4P_BYTES or sha256_file(selected_s4p) != S4P_SHA256:
        raise FreshReplayError("source_identity:exact_selected_s4p_required")
    if ads_reference.stat().st_size != ADS_BYTES or sha256_file(ads_reference) != ADS_SHA256:
        raise FreshReplayError("reference_identity:exact_ads_payload_required")
    if not product_cli.is_file():
        raise FreshReplayError("product_cli:executable_missing")

    custody = tempfile.TemporaryDirectory(prefix="sipi-p3c-current-replay-")
    custody_root = Path(custody.name)
    try:
        archive = custody_root / "archive"
        materialize_clean_archive(commit, archive)
        if not (archive / RUNNER_RELATIVE_PATH).is_file():
            raise FreshReplayError("runner:clean_archive_runner_missing")
        child_report = custody_root / "child-report.json"
        _run_child(archive, selected_s4p, ads_reference, product_cli, child_report)
        payload = child_report.read_bytes()
        child = assert_child_report(json.loads(payload.decode("ascii")))
        child_digest = sha256_bytes(payload)
        runs = child["fresh_runs"]
        assert isinstance(runs, list)
        summary = {
            "schema": SUMMARY_SCHEMA,
            "status": "prepared_observed_not_accepted",
            "clean_archive_commit": commit,
            "clean_archive_tree": tree,
            "runner_path": RUNNER_RELATIVE_PATH.as_posix(),
            "runner_test": RUNNER_TEST,
            "cli_sha256": sha256_file(product_cli),
            "selected_s4p": {"byte_length": S4P_BYTES, "sha256": S4P_SHA256},
            "ads_reference": {"byte_length": ADS_BYTES, "sha256": ADS_SHA256},
            "fresh_replay_runs": 2,
            "fresh_custody_runs": 2,
            "source_manifest_sha256s": [run["source_manifest_sha256"] for run in runs],
            "reference_manifest_sha256s": [run["reference_manifest_sha256"] for run in runs],
            "candidate_manifest_sha256s": [run["candidate_manifest_sha256"] for run in runs],
            "candidate_payload_sha256": runs[0]["candidate_payload_sha256"],
            "strict_index": {
                "stage": "strict_index_waveform_only_compare_v3",
                "start_index": 32704,
                "sample_count": 16352,
                "alignment": "prohibited",
                "within_one_percent": False,
                "rejection": "strict_index_waveform_nrmse_limit",
            },
            "child_report_sha256": child_digest,
            "report": "hash_only_no_payload_or_absolute_path",
            "cleanup_status": "complete",
            "evidence_promotion": False,
        }
    finally:
        custody.cleanup()
    if custody_root.exists():
        raise FreshReplayError("cleanup:temporary_custody_root_retained")
    return summary


def write_summary(path: Path, summary: dict[str, object]) -> tuple[int, str]:
    destination = require_external(path, kind="report", exists=False)
    payload = (json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return len(payload), sha256_bytes(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--s4p", required=True, type=Path)
    parser.add_argument("--ads-reference", required=True, type=Path)
    parser.add_argument("--cli", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        summary = observe_fresh(
            commit=args.commit,
            source=args.s4p,
            reference=args.ads_reference,
            cli=args.cli,
        )
        byte_length, digest = write_summary(args.report, summary)
        print(json.dumps({"status": "prepared", "report_byte_length": byte_length, "report_sha256": digest}, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError, UnicodeError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
