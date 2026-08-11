"""Bind one fixed TRAN performance observation to a provisional P7 candidate chain."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p7-fixed-tran-candidate-performance-evaluation.v1"
POLICY_PATH = ROOT / "docs" / "baselines" / "fixed-tran-performance-policy.v1.yaml"


class CandidateError(RuntimeError):
    pass


def _load_module(name: str, filename: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    if specification is None or specification.loader is None:
        raise CandidateError("supporting_verifier_unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


POLICY = _load_module("p7_fixed_policy", "verify_p7_fixed_tran_performance_policy.py")
COMPOSITION = _load_module("p7_composition", "verify_p7_release_composition.py")
ARCHIVE = _load_module("p7_archive", "verify_p7_release_archive.py")
INSTALL = _load_module("p7_install", "verify_p7_isolated_install.py")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _external(path: Path) -> bool:
    resolved = path.resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateError("evidence_json_invalid") from error
    if not isinstance(document, dict):
        raise CandidateError("evidence_json_invalid")
    return document, payload


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _git_text(*arguments: str) -> str:
    try:
        completed = subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise CandidateError("git_identity_unavailable") from error
    return completed.stdout.decode("ascii").strip()


def _parse_archive_entries(document: dict[str, Any]) -> tuple[str, int]:
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 2:
        raise CandidateError("archive_entries_invalid")
    by_role: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"role", "bytes", "content_sha256"}:
            raise CandidateError("archive_entries_invalid")
        role = entry.get("role")
        if not isinstance(role, str) or role in by_role or not isinstance(entry.get("bytes"), int) or entry["bytes"] <= 0 or not _hex(entry.get("content_sha256")):
            raise CandidateError("archive_entries_invalid")
        by_role[role] = entry
    if set(by_role) != {"main_executable", "mit_license"}:
        raise CandidateError("archive_entries_invalid")
    return by_role["main_executable"]["content_sha256"], by_role["main_executable"]["bytes"]


def _parse_install(document: object) -> dict[str, Any]:
    expected = {
        "schema", "status", "environment_class", "fresh_machine", "fresh_user", "host_loader_closure",
        "promotion_status", "archive_sha256", "archive_report_sha256", "installed_executable_sha256",
        "sanitization_policy_sha256", "probes", "limitations",
    }
    if (
        not isinstance(document, dict)
        or set(document) != expected
        or document.get("schema") != "sipi.isolated-install-admission.v1"
        or document.get("status") != "isolated_install_smoke_passed"
        or document.get("environment_class") != "same_host_isolated_prefix"
        or document.get("fresh_machine") is not False
        or document.get("fresh_user") != "not_assessed"
        or document.get("host_loader_closure") != "not_assessed"
        or document.get("promotion_status") != "blocked"
        or not all(_hex(document.get(key)) for key in ("archive_sha256", "archive_report_sha256", "installed_executable_sha256", "sanitization_policy_sha256"))
        or not isinstance(document.get("probes"), list)
        or not document["probes"]
        or not isinstance(document.get("limitations"), list)
        or not document["limitations"]
    ):
        raise CandidateError("install_report_invalid")
    return document


def evaluate_candidate(
    *,
    policy: dict[str, Any],
    policy_sha256: str,
    policy_baseline: dict[str, Any],
    policy_baseline_sha256: str,
    policy_locked_build: dict[str, Any],
    policy_locked_build_sha256: str,
    candidate_observation: dict[str, Any],
    candidate_observation_sha256: str,
    twin: dict[str, Any],
    twin_sha256: str,
    composition: dict[str, Any],
    composition_sha256: str,
    archive: dict[str, Any],
    archive_sha256: str,
    install: dict[str, Any],
    install_sha256: str,
    head: str,
    tree: str,
) -> dict[str, Any]:
    if not _hex(policy_sha256):
        raise CandidateError("policy_digest_invalid")
    policy_report = POLICY.validate_policy(
        policy,
        policy_baseline,
        policy_baseline_sha256,
        policy_locked_build,
        policy_locked_build_sha256,
    )
    if not policy_report.get("valid"):
        raise CandidateError("policy_baseline_not_bound")
    observation = POLICY.MEASURE.validate_observation(candidate_observation)
    if not observation.get("valid") or not _hex(candidate_observation_sha256):
        raise CandidateError("candidate_observation_invalid")
    try:
        twin_identity = COMPOSITION.parse_twin_report(twin)
        composition_identity = ARCHIVE.parse_composition(composition)
        archive_identity = INSTALL.parse_prior_report(archive)
    except (COMPOSITION.PreflightError, ARCHIVE.ArchiveError, INSTALL.InstallError) as error:
        raise CandidateError("candidate_chain_invalid") from error
    install_identity = _parse_install(install)
    if not all(_hex(value) for value in (twin_sha256, composition_sha256, archive_sha256, install_sha256)):
        raise CandidateError("candidate_chain_digest_invalid")
    if (
        head != twin_identity["commit"]
        or tree != twin_identity["tree"]
        or composition_identity["twin_report_sha256"] != twin_sha256
        or composition_identity["commit"] != twin_identity["commit"]
        or composition_identity["tree"] != twin_identity["tree"]
        or composition_identity["cargo_lock_sha256"] != twin_identity["lock_sha256"]
        or composition_identity["toolchain_sha256"] != twin_identity["toolchain_sha256"]
        or composition_identity["staged_binary_sha256"] != twin_identity["binary_sha256"]
        or composition_identity["staged_binary_bytes"] != twin_identity["binary_bytes"]
    ):
        raise CandidateError("twin_composition_identity_mismatch")
    executable_sha256, executable_bytes = _parse_archive_entries(archive_identity)
    if (
        archive_identity["composition_report_sha256"] != composition_sha256
        or archive_identity["source_commit"] != composition_identity["commit"]
        or executable_sha256 != composition_identity["staged_binary_sha256"]
        or executable_bytes != composition_identity["staged_binary_bytes"]
        or install_identity["archive_sha256"] != archive_identity["archive_sha256"]
        or install_identity["archive_report_sha256"] != archive_sha256
        or install_identity["installed_executable_sha256"] != executable_sha256
    ):
        raise CandidateError("archive_install_identity_mismatch")
    observed_identity = candidate_observation["identity"]
    if (
        observed_identity["commit"] != composition_identity["commit"]
        or observed_identity["cargo_lock_sha256"] != composition_identity["cargo_lock_sha256"]
        or observed_identity["executable_sha256"] != executable_sha256
    ):
        raise CandidateError("candidate_observation_chain_mismatch")
    medians = {
        "wall_time_ns": candidate_observation["summary"]["wall_time_ns"]["median"],
        "peak_working_set_bytes": candidate_observation["summary"]["peak_working_set_bytes"]["median"],
    }
    thresholds = policy["thresholds"]
    within_policy = (
        medians["wall_time_ns"] <= thresholds["median_wall_time_ns_max"]
        and medians["peak_working_set_bytes"] <= thresholds["median_peak_working_set_bytes_max"]
    )
    return {
        "schema": SCHEMA,
        "status": "within_policy" if within_policy else "over_limit",
        "promotion_status": "blocked",
        "policy_sha256": policy_sha256,
        "observation_sha256": candidate_observation_sha256,
        "candidate_chain": {
            "twin_report_sha256": twin_sha256,
            "commit": twin_identity["commit"],
            "tree": twin_identity["tree"],
            "cargo_lock_sha256": twin_identity["lock_sha256"],
            "toolchain_sha256": twin_identity["toolchain_sha256"],
            "executable_sha256": executable_sha256,
            "composition_report_sha256": composition_sha256,
            "staged_binary_sha256": composition_identity["staged_binary_sha256"],
            "archive_report_sha256": archive_sha256,
            "archive_sha256": archive_identity["archive_sha256"],
            "archive_entry_binary_sha256": executable_sha256,
            "install_report_sha256": install_sha256,
            "installed_executable_sha256": install_identity["installed_executable_sha256"],
        },
        "observed_medians": medians,
        "thresholds": thresholds,
        "threshold_verdict": "pass" if within_policy else "block_release_candidate",
        "limitations": [
            "candidate performance evidence only; promotion remains blocked",
            "not a hard CPU, RSS, OOM, cross-machine, service, or GUI performance guarantee",
            "independent license, NOTICE, fresh-machine, asset, and profile gates remain blocked",
        ],
    }


def _write_new_external(path: Path, report: dict[str, Any]) -> None:
    if not _external(path) or path.exists() or path.is_symlink():
        raise CandidateError("external_new_report_required")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as output:
            output.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError as error:
        raise CandidateError("candidate_report_write_failed") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--policy-baseline-observation", type=Path, required=True)
    parser.add_argument("--policy-p1-locked-build-report", type=Path, required=True)
    parser.add_argument("--candidate-observation", type=Path, required=True)
    parser.add_argument("--twin-report", type=Path, required=True)
    parser.add_argument("--composition-report", type=Path, required=True)
    parser.add_argument("--archive-report", type=Path, required=True)
    parser.add_argument("--install-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        evidence_paths = (
            arguments.policy_baseline_observation,
            arguments.policy_p1_locked_build_report,
            arguments.candidate_observation,
            arguments.twin_report,
            arguments.composition_report,
            arguments.archive_report,
            arguments.install_report,
        )
        if not all(_external(path) for path in evidence_paths):
            raise CandidateError("external_evidence_required")
        policy, policy_bytes = _load_json(arguments.policy)
        baseline, baseline_bytes = _load_json(arguments.policy_baseline_observation)
        locked_build, locked_build_bytes = _load_json(arguments.policy_p1_locked_build_report)
        candidate, candidate_bytes = _load_json(arguments.candidate_observation)
        twin, twin_bytes = _load_json(arguments.twin_report)
        composition, composition_bytes = _load_json(arguments.composition_report)
        archive, archive_bytes = _load_json(arguments.archive_report)
        install, install_bytes = _load_json(arguments.install_report)
        report = evaluate_candidate(
            policy=policy,
            policy_sha256=sha256(policy_bytes),
            policy_baseline=baseline,
            policy_baseline_sha256=sha256(baseline_bytes),
            policy_locked_build=locked_build,
            policy_locked_build_sha256=sha256(locked_build_bytes),
            candidate_observation=candidate,
            candidate_observation_sha256=sha256(candidate_bytes),
            twin=twin,
            twin_sha256=sha256(twin_bytes),
            composition=composition,
            composition_sha256=sha256(composition_bytes),
            archive=archive,
            archive_sha256=sha256(archive_bytes),
            install=install,
            install_sha256=sha256(install_bytes),
            head=_git_text("rev-parse", "HEAD"),
            tree=_git_text("rev-parse", "HEAD^{tree}"),
        )
        _write_new_external(arguments.report, report)
    except CandidateError as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "within_policy" else 2


if __name__ == "__main__":
    raise SystemExit(main())
