"""Verify a hash-only, provisional v2 P7 evidence anchor."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "baselines" / "p7-evidence-anchor.v2.yaml"
DOCUMENT_PATH = "docs/baselines/p7-evidence-anchor.v2.yaml"
SCHEMA = "sipi.p7-evidence-anchor.v2"
REQUIRED_BLOCKERS = {
    "license_notice_pending",
    "fresh_machine_evidence_missing",
    "uncertified_domain_profiles",
}
REPORT_KEYS = (
    "twin_report",
    "layout_report",
    "composition_report",
    "archive_report",
    "install_report",
    "performance_observation",
    "candidate_evaluation",
)
MAX_EXTERNAL_REPORT_BYTES = 128 * 1024


class ObservationError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: object, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length or any(character not in "0123456789abcdef" for character in value):
        raise ObservationError("invalid_digest")
    return value


def _load_json(path: Path, reason: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError(reason) from error
    if not isinstance(document, dict):
        raise ObservationError(reason)
    return document, raw


def _git_text(*arguments: str) -> str:
    try:
        completed = subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True)
        return completed.stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ObservationError("candidate_git_identity_invalid") from error


def _git_archived_member_sha256(commit: str, path: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "archive", "--format=tar", commit, path],
            check=True,
            capture_output=True,
        )
        with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as bundle:
            member = bundle.getmember(path)
            if not member.isfile() or member.issym() or member.islnk():
                raise ObservationError("candidate_input_unavailable")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ObservationError("candidate_input_unavailable")
            return sha256_bytes(stream.read())
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, KeyError) as error:
        if isinstance(error, ObservationError):
            raise
        raise ObservationError("candidate_input_unavailable") from error


def _candidate_lacks_record(commit: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}:{DOCUMENT_PATH}"],
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return False
    if completed.returncode == 128:
        return True
    raise ObservationError("candidate_record_separation_unavailable")


def _safe_audit_ref(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("docs/baselines/audits/") or not value.endswith(".md"):
        raise ObservationError("audit_reference_invalid")
    if "\\" in value or ":" in value or "\0" in value or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ObservationError("audit_reference_invalid")
    return value


def _validate_report_ref(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"sha256", "bytes"}:
        raise ObservationError("report_reference_invalid")
    _hex(value.get("sha256"))
    if not isinstance(value.get("bytes"), int) or value["bytes"] <= 0:
        raise ObservationError("report_reference_invalid")
    return value


def validate(document: dict[str, Any]) -> None:
    expected = {
        "schema", "kind", "candidate_source_commit", "candidate_tree", "candidate_cargo_lock_sha256",
        "candidate_toolchain_sha256", "candidate_executable", "recording", "evidence", "chain_state",
        "global_blockers", "audit_ref", "non_claims",
    }
    if set(document) != expected or document.get("schema") != SCHEMA or document.get("kind") != "evidence_anchor_not_release":
        raise ObservationError("document_schema_invalid")
    commit = _hex(document.get("candidate_source_commit"), 40)
    tree = _hex(document.get("candidate_tree"), 40)
    for key in ("candidate_cargo_lock_sha256", "candidate_toolchain_sha256"):
        _hex(document.get(key))
    executable = document.get("candidate_executable")
    if (
        not isinstance(executable, dict)
        or set(executable) != {"sha256", "bytes", "platform"}
        or executable.get("platform") != "windows-x86_64"
        or not isinstance(executable.get("bytes"), int)
        or executable["bytes"] <= 0
    ):
        raise ObservationError("candidate_executable_invalid")
    _hex(executable.get("sha256"))
    if _git_text("cat-file", "-t", commit) != "commit" or _git_text("rev-parse", f"{commit}^{{tree}}") != tree:
        raise ObservationError("candidate_git_identity_invalid")
    if _git_archived_member_sha256(commit, "Cargo.lock") != document["candidate_cargo_lock_sha256"]:
        raise ObservationError("candidate_lock_mismatch")
    if _git_archived_member_sha256(commit, "rust-toolchain.toml") != document["candidate_toolchain_sha256"]:
        raise ObservationError("candidate_toolchain_mismatch")
    if document.get("recording") != {
        "candidate_tree_excludes_this_record": True,
        "evidence_subject_is_candidate_source_commit_not_record_commit": True,
    } or not _candidate_lacks_record(commit):
        raise ObservationError("candidate_record_separation_invalid")

    evidence = document.get("evidence")
    expected_evidence = {"layout_policy_sha256", "performance_policy_sha256", *REPORT_KEYS}
    if not isinstance(evidence, dict) or set(evidence) != expected_evidence:
        raise ObservationError("evidence_schema_invalid")
    for key in ("layout_policy_sha256", "performance_policy_sha256"):
        _hex(evidence.get(key))
    for key in REPORT_KEYS:
        _validate_report_ref(evidence.get(key))

    expected_chain = {
        "twin_build": "identical",
        "static_layout": "layout_conformant",
        "composition_evidence_status": "incomplete",
        "archive_structural_admission": "conformant",
        "install_environment_class": "same_host_isolated_prefix",
        "performance_status": "observed_pending_owner_budget",
        "performance_threshold_verdict": "pass",
        "candidate_evaluation_status": "within_policy",
        "promotion_status": "blocked",
        "release_candidate": False,
    }
    if document.get("chain_state") != expected_chain:
        raise ObservationError("chain_state_invalid")
    blockers = document.get("global_blockers")
    if not isinstance(blockers, list) or len(blockers) != len(set(blockers)) or set(blockers) != REQUIRED_BLOCKERS:
        raise ObservationError("global_blockers_invalid")
    audit_ref = _safe_audit_ref(document.get("audit_ref"))
    if not (ROOT / audit_ref).is_file():
        raise ObservationError("audit_reference_unavailable")
    expected_non_claims = [
        "not_a_release_tag_or_candidate",
        "not_a_release_approval_or_license_notice_clearance",
        "not_a_fresh_machine_or_fresh_user_certification",
        "not_a_dynamic_or_runtime_dependency_closure",
        "not_a_cross_platform_or_profile_certification",
    ]
    if document.get("non_claims") != expected_non_claims:
        raise ObservationError("non_claims_invalid")


def validate_introduction(document: dict[str, Any], raw: bytes) -> str:
    """Prove that this immutable candidate predates the anchor's introduction."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--diff-filter=A", "--format=%H", "--", DOCUMENT_PATH],
            check=True,
            capture_output=True,
        )
        introductions = [line for line in completed.stdout.decode("ascii").splitlines() if line]
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ObservationError("anchor_introduction_unavailable") from error
    if len(introductions) != 1:
        raise ObservationError("anchor_introduction_invalid")
    record_commit = _hex(introductions[0], 40)
    candidate_commit = document["candidate_source_commit"]
    if record_commit == candidate_commit:
        raise ObservationError("anchor_record_candidate_not_distinct")
    ancestry = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", candidate_commit, record_commit],
        capture_output=True,
        check=False,
    )
    if ancestry.returncode != 0:
        raise ObservationError("anchor_candidate_not_record_ancestor")
    try:
        introduced = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{record_commit}:{DOCUMENT_PATH}"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ObservationError("anchor_introduction_unavailable") from error
    if introduced != raw:
        raise ObservationError("anchor_modified_after_introduction")
    return record_commit


def _read_external(path: Path, reason: str) -> bytes:
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ObservationError("external_evidence_required")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or before.st_size <= 0 or before.st_size > MAX_EXTERNAL_REPORT_BYTES:
            raise ObservationError("external_evidence_required")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise ObservationError(reason) from error
    if before.st_size != len(raw) or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ObservationError("external_evidence_changed_during_read")
    return raw


def _external_json(path: Path, reference: dict[str, object], reason: str) -> dict[str, Any]:
    raw = _read_external(path, reason)
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError(reason) from error
    if not isinstance(document, dict):
        raise ObservationError(reason)
    if sha256_bytes(raw) != reference["sha256"] or len(raw) != reference["bytes"]:
        raise ObservationError(f"{reason}_identity_mismatch")
    return document


def _require_exact_keys(document: object, keys: set[str], schema: str, reason: str) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != keys or document.get("schema") != schema:
        raise ObservationError(reason)
    return document


def verify_external_observation(
    document: dict[str, Any],
    *,
    layout_policy: Path,
    twin_report: Path,
    layout_report: Path,
    composition_report: Path,
    archive_report: Path,
    install_report: Path,
    performance_observation: Path,
    candidate_evaluation: Path,
) -> None:
    evidence = document["evidence"]
    policy_raw = _read_external(layout_policy, "layout_policy_invalid")
    if sha256_bytes(policy_raw) != evidence["layout_policy_sha256"]:
        raise ObservationError("layout_policy_identity_mismatch")
    try:
        policy = json.loads(policy_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("layout_policy_invalid") from error
    if not isinstance(policy, dict) or policy.get("schema") != "sipi.release-layout-policy.v1" or "bcryptprimitives.dll" not in policy.get("normalImportDllAllowlist", []):
        raise ObservationError("layout_policy_invalid")

    twin = _external_json(twin_report, evidence["twin_report"], "twin_report")
    layout = _external_json(layout_report, evidence["layout_report"], "layout_report")
    composition = _external_json(composition_report, evidence["composition_report"], "composition_report")
    archive = _external_json(archive_report, evidence["archive_report"], "archive_report")
    install = _external_json(install_report, evidence["install_report"], "install_report")
    performance = _external_json(performance_observation, evidence["performance_observation"], "performance_observation")
    evaluation = _external_json(candidate_evaluation, evidence["candidate_evaluation"], "candidate_evaluation")

    candidate = {
        "commit": document["candidate_source_commit"],
        "tree": document["candidate_tree"],
        "lock": document["candidate_cargo_lock_sha256"],
        "toolchain": document["candidate_toolchain_sha256"],
        "exe": document["candidate_executable"]["sha256"],
        "bytes": document["candidate_executable"]["bytes"],
    }
    twin = _require_exact_keys(twin, {"schema", "status", "commit", "tree", "lock_sha256", "toolchain_sha256", "rustflags_sha256", "target", "build_a", "build_b", "comparison", "limitations"}, "sipi.p7-windows-twin-build-report.v1", "twin_report_schema_invalid")
    if twin.get("status") != "identical" or twin.get("target") != "x86_64-pc-windows-msvc" or twin.get("comparison") != {"size_match": True, "digest_match": True}:
        raise ObservationError("twin_report_content_invalid")
    if {"commit": twin.get("commit"), "tree": twin.get("tree"), "lock": twin.get("lock_sha256"), "toolchain": twin.get("toolchain_sha256")} != {key: candidate[key] for key in ("commit", "tree", "lock", "toolchain")}:
        raise ObservationError("twin_candidate_binding_invalid")
    for key in ("build_a", "build_b"):
        build = twin.get(key)
        if not isinstance(build, dict) or build.get("binary_sha256") != candidate["exe"] or build.get("binary_bytes") != candidate["bytes"]:
            raise ObservationError("twin_binary_binding_invalid")

    layout = _require_exact_keys(layout, {"schema", "status", "policySha256", "inventorySha256", "executableSha256", "executableBytes", "machine", "normalImports", "delayImportDirectoryPresent", "smoke", "limitations"}, "sipi.release-layout-report.v1", "layout_report_schema_invalid")
    if layout.get("status") != "layout_conformant" or layout.get("policySha256") != evidence["layout_policy_sha256"] or layout.get("executableSha256") != candidate["exe"] or layout.get("executableBytes") != candidate["bytes"] or layout.get("machine") != "amd64" or layout.get("delayImportDirectoryPresent") is not False:
        raise ObservationError("layout_candidate_binding_invalid")

    composition = _require_exact_keys(composition, {"schema", "source_build", "static_pe", "dependency_inventory", "notice_license_gaps", "evidence_status", "promotion_status", "limitations"}, "sipi.release-composition-preflight.v1", "composition_report_schema_invalid")
    source_build = composition.get("source_build")
    if not isinstance(source_build, dict) or composition.get("evidence_status") != "incomplete" or composition.get("promotion_status") != "blocked" or source_build.get("commit") != candidate["commit"] or source_build.get("tree") != candidate["tree"] or source_build.get("cargo_lock_sha256") != candidate["lock"] or source_build.get("toolchain_sha256") != candidate["toolchain"] or source_build.get("staged_binary_sha256") != candidate["exe"] or source_build.get("staged_binary_bytes") != candidate["bytes"] or source_build.get("twin_report_sha256") != evidence["twin_report"]["sha256"]:
        raise ObservationError("composition_candidate_binding_invalid")

    archive = _require_exact_keys(archive, {"schema", "structural_admission", "composition_evidence_status", "promotion_status", "archive_sha256", "archive_bytes", "policy_sha256", "composition_report_sha256", "source_commit", "entries", "static_pe_binding", "limitations"}, "sipi.release-archive-report.v1", "archive_report_schema_invalid")
    if archive.get("structural_admission") != "conformant" or archive.get("composition_evidence_status") != "incomplete" or archive.get("promotion_status") != "blocked" or archive.get("composition_report_sha256") != evidence["composition_report"]["sha256"] or archive.get("source_commit") != candidate["commit"]:
        raise ObservationError("archive_candidate_binding_invalid")

    install = _require_exact_keys(install, {"schema", "status", "environment_class", "fresh_machine", "fresh_user", "host_loader_closure", "promotion_status", "archive_sha256", "archive_report_sha256", "installed_executable_sha256", "sanitization_policy_sha256", "probes", "limitations"}, "sipi.isolated-install-admission.v1", "install_report_schema_invalid")
    if install.get("status") != "isolated_install_smoke_passed" or install.get("environment_class") != "same_host_isolated_prefix" or install.get("fresh_machine") is not False or install.get("fresh_user") != "not_assessed" or install.get("host_loader_closure") != "not_assessed" or install.get("promotion_status") != "blocked" or install.get("archive_sha256") != archive.get("archive_sha256") or install.get("archive_report_sha256") != evidence["archive_report"]["sha256"] or install.get("installed_executable_sha256") != candidate["exe"]:
        raise ObservationError("install_candidate_binding_invalid")

    performance = _require_exact_keys(performance, {"schema", "status", "identity", "workload", "protocol", "samples", "summary", "limitations"}, "sipi.tran.performance-observation.v1", "performance_report_schema_invalid")
    identity = performance.get("identity")
    if not isinstance(identity, dict) or performance.get("status") != "observed_pending_owner_budget" or performance.get("protocol") != {"warmup_count": 3, "measured_count": 10, "wall_clock": "perf_counter_ns", "peak_working_set": "GetProcessMemoryInfo.PeakWorkingSetSize"} or identity.get("commit") != candidate["commit"] or identity.get("cargo_lock_sha256") != candidate["lock"] or identity.get("executable_sha256") != candidate["exe"] or identity.get("executable_bytes") != candidate["bytes"]:
        raise ObservationError("performance_candidate_binding_invalid")

    evaluation = _require_exact_keys(evaluation, {"schema", "status", "promotion_status", "policy_sha256", "observation_sha256", "candidate_chain", "observed_medians", "thresholds", "threshold_verdict", "limitations"}, "sipi.p7-fixed-tran-candidate-performance-evaluation.v1", "evaluation_report_schema_invalid")
    chain = evaluation.get("candidate_chain")
    if not isinstance(chain, dict) or evaluation.get("status") != "within_policy" or evaluation.get("threshold_verdict") != "pass" or evaluation.get("promotion_status") != "blocked" or evaluation.get("policy_sha256") != evidence["performance_policy_sha256"] or evaluation.get("observation_sha256") != evidence["performance_observation"]["sha256"]:
        raise ObservationError("evaluation_state_invalid")
    expected_chain = {
        "commit": candidate["commit"], "tree": candidate["tree"], "cargo_lock_sha256": candidate["lock"],
        "toolchain_sha256": candidate["toolchain"], "executable_sha256": candidate["exe"],
        "staged_binary_sha256": candidate["exe"], "archive_entry_binary_sha256": candidate["exe"],
        "installed_executable_sha256": candidate["exe"], "twin_report_sha256": evidence["twin_report"]["sha256"],
        "composition_report_sha256": evidence["composition_report"]["sha256"], "archive_report_sha256": evidence["archive_report"]["sha256"],
        "install_report_sha256": evidence["install_report"]["sha256"], "archive_sha256": archive.get("archive_sha256"),
    }
    if chain != expected_chain:
        raise ObservationError("evaluation_chain_binding_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", type=Path, default=DOCUMENT)
    parser.add_argument("--layout-policy", type=Path)
    parser.add_argument("--twin-report", type=Path)
    parser.add_argument("--layout-report", type=Path)
    parser.add_argument("--composition-report", type=Path)
    parser.add_argument("--archive-report", type=Path)
    parser.add_argument("--install-report", type=Path)
    parser.add_argument("--performance-observation", type=Path)
    parser.add_argument("--candidate-evaluation", type=Path)
    parser.add_argument("--skip-introduction-check", action="store_true")
    arguments = parser.parse_args()
    try:
        document, raw = _load_json(arguments.document, "document_json_invalid")
        validate(document)
        record_commit = None if arguments.skip_introduction_check else validate_introduction(document, raw)
        external = (
            arguments.layout_policy, arguments.twin_report, arguments.layout_report, arguments.composition_report,
            arguments.archive_report, arguments.install_report, arguments.performance_observation,
            arguments.candidate_evaluation,
        )
        if any(path is not None for path in external):
            if any(path is None for path in external):
                raise ObservationError("paired_external_evidence_required")
            verify_external_observation(document, **{
                "layout_policy": arguments.layout_policy,
                "twin_report": arguments.twin_report,
                "layout_report": arguments.layout_report,
                "composition_report": arguments.composition_report,
                "archive_report": arguments.archive_report,
                "install_report": arguments.install_report,
                "performance_observation": arguments.performance_observation,
                "candidate_evaluation": arguments.candidate_evaluation,
            })
        result = {"schema": SCHEMA, "valid": True, "document_sha256": sha256_bytes(raw)}
        if record_commit is not None:
            result["record_commit"] = record_commit
        print(json.dumps(result, sort_keys=True))
        return 0
    except ObservationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
