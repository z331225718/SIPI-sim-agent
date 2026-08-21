"""Verify the hash-only P7 chain that was rejected at candidate evaluation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "baselines" / "p7-current-candidate-chain-rejected-evaluation.v1.yaml"
DOCUMENT_PATH = "docs/baselines/p7-current-candidate-chain-rejected-evaluation.v1.yaml"
SCHEMA = "sipi.p7-current-candidate-chain-rejected-evaluation.v1"
MAX_EXTERNAL_BYTES = 128 * 1024
REQUIRED_BLOCKERS = {
    "license_notice_pending",
    "fresh_machine_evidence_missing",
    "uncertified_domain_profiles",
    "performance_baseline_custody_unavailable",
    "current_candidate_p7_chain_not_admitted",
}
REPORT_KEYS = (
    "layout_policy",
    "twin_report",
    "layout_report",
    "composition_report",
    "archive_report",
    "install_report",
    "performance_observation",
    "evaluation_rejection_output",
)


class ChainError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: object, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length or any(char not in "0123456789abcdef" for char in value):
        raise ChainError("invalid_digest")
    return value


def _load_json(path: Path, reason: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChainError(reason) from error
    if not isinstance(document, dict):
        raise ChainError(reason)
    return document, raw


def _load_module(name: str, filename: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    if specification is None or specification.loader is None:
        raise ChainError("supporting_verifier_unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _git_text(*arguments: str) -> str:
    try:
        completed = subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True)
        return completed.stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ChainError("candidate_git_identity_invalid") from error


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
                raise ChainError("candidate_input_unavailable")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ChainError("candidate_input_unavailable")
            return sha256_bytes(stream.read())
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, KeyError) as error:
        raise ChainError("candidate_input_unavailable") from error


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
    raise ChainError("candidate_record_separation_unavailable")


def _safe_ref(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("docs/baselines/audits/") or not value.endswith(".md"):
        raise ChainError("audit_reference_invalid")
    if "\\" in value or ":" in value or "\0" in value or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ChainError("audit_reference_invalid")
    return value


def _validate_ref(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"sha256", "bytes"}:
        raise ChainError("report_reference_invalid")
    _hex(value.get("sha256"))
    if not isinstance(value.get("bytes"), int) or value["bytes"] <= 0:
        raise ChainError("report_reference_invalid")
    return value


def _contains_forbidden_identity(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "report_path", "external_root", "hostname", "host_name", "user", "username", "machine_id"}:
                return True
            if _contains_forbidden_identity(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_identity(item) for item in value)
    return False


def validate(document: dict[str, Any]) -> None:
    expected = {
        "schema", "kind", "candidate_source_commit", "candidate_tree", "candidate_cargo_lock_sha256",
        "candidate_toolchain_sha256", "candidate_executable", "recording", "evidence", "stage_observations",
        "performance_policy_custody", "chain_state", "gate_summary", "global_blockers", "promotion_status",
        "release_candidate", "non_claims", "audit_ref",
    }
    if set(document) != expected or document.get("schema") != SCHEMA or document.get("kind") != "current_chain_rejected_at_evaluation_not_release":
        raise ChainError("document_schema_invalid")
    if _contains_forbidden_identity(document):
        raise ChainError("machine_identity_or_path_retained")
    commit = _hex(document.get("candidate_source_commit"), 40)
    tree = _hex(document.get("candidate_tree"), 40)
    for key in ("candidate_cargo_lock_sha256", "candidate_toolchain_sha256"):
        _hex(document.get(key))
    if _git_text("cat-file", "-t", commit) != "commit" or _git_text("rev-parse", f"{commit}^{{tree}}") != tree:
        raise ChainError("candidate_git_identity_invalid")
    if _git_archived_member_sha256(commit, "Cargo.lock") != document["candidate_cargo_lock_sha256"]:
        raise ChainError("candidate_lock_mismatch")
    if _git_archived_member_sha256(commit, "rust-toolchain.toml") != document["candidate_toolchain_sha256"]:
        raise ChainError("candidate_toolchain_mismatch")
    recording = document.get("recording")
    if recording != {
        "candidate_tree_excludes_this_record": True,
        "evidence_subject_is_candidate_source_commit_not_record_commit": True,
        "external_reports_and_payloads_retained_outside_repository": True,
        "machine_identity_retained": False,
    } or not _candidate_lacks_record(commit):
        raise ChainError("candidate_record_separation_invalid")

    executable = document.get("candidate_executable")
    if not isinstance(executable, dict) or set(executable) != {"sha256", "bytes", "platform"} or executable.get("platform") != "windows-x86_64" or not isinstance(executable.get("bytes"), int) or executable["bytes"] <= 0:
        raise ChainError("candidate_executable_invalid")
    _hex(executable.get("sha256"))

    evidence = document.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(REPORT_KEYS):
        raise ChainError("evidence_schema_invalid")
    for key in REPORT_KEYS:
        _validate_ref(evidence.get(key))

    stages = document.get("stage_observations")
    expected_stages = {"twin_build", "static_layout", "composition", "archive", "isolated_install", "performance", "evaluation"}
    if not isinstance(stages, dict) or set(stages) != expected_stages:
        raise ChainError("stage_observations_invalid")
    if stages["twin_build"] != {"status": "identical", "binary_sha256": executable["sha256"], "binary_bytes": executable["bytes"]}:
        raise ChainError("twin_stage_invalid")
    if stages["static_layout"] != {
        "status": "layout_conformant",
        "policy_sha256": evidence["layout_policy"]["sha256"],
        "executable_sha256": executable["sha256"],
        "executable_bytes": executable["bytes"],
        "delay_import_directory_present": False,
    }:
        raise ChainError("layout_stage_invalid")
    if stages["composition"] != {"evidence_status": "incomplete", "promotion_status": "blocked"}:
        raise ChainError("composition_stage_invalid")
    if stages["archive"] != {
        "structural_admission": "conformant",
        "composition_evidence_status": "incomplete",
        "promotion_status": "blocked",
        "archive_sha256": "d7703795da9b225ca37d110bafbc4d93e9b6e945dbbf50197749501ec30f30df",
        "archive_bytes": 1232644,
    }:
        raise ChainError("archive_stage_invalid")
    if stages["isolated_install"] != {
        "status": "isolated_install_smoke_passed",
        "environment_class": "same_host_isolated_prefix",
        "fresh_machine": False,
        "fresh_user": "not_assessed",
        "host_loader_closure": "not_assessed",
        "promotion_status": "blocked",
    }:
        raise ChainError("install_stage_invalid")
    performance = stages["performance"]
    if not isinstance(performance, dict) or performance.get("status") != "observed_pending_owner_budget" or performance.get("protocol") != {
        "warmup_count": 3,
        "measured_count": 10,
        "wall_clock": "perf_counter_ns",
        "peak_working_set": "GetProcessMemoryInfo.PeakWorkingSetSize",
    } or performance.get("observed_medians") != {"wall_time_ns": 26349750, "peak_working_set_bytes": 4681728} or performance.get("numeric_observation_under_delegated_thresholds") is not True or performance.get("policy_verdict") != "not_evaluated":
        raise ChainError("performance_stage_invalid")
    if stages["evaluation"] != {"report_present": False, "status": "rejected", "reason": "evidence_json_invalid"}:
        raise ChainError("evaluation_stage_invalid")

    custody = document.get("performance_policy_custody")
    if not isinstance(custody, dict) or set(custody) != {"policy_sha256", "required_baseline_observation_sha256", "required_p1_locked_build_report_sha256", "status", "evaluation_blocker"} or custody.get("policy_sha256") != "700abb092a2da02331ff93407965d7e2414a3f14832def90127d0cc361645d28" or custody.get("required_baseline_observation_sha256") != "f6bcef3ee820919062018a6c3d37128260ca4cc28e8bb8c8867e3e98d060ae4f" or custody.get("required_p1_locked_build_report_sha256") != "a17d68e504d5112b401aac970431e31460db67faecc975a19fe0d1bb6a9de1f7" or custody.get("status") != "historical_baseline_custody_unavailable" or custody.get("evaluation_blocker") != "evidence_json_invalid":
        raise ChainError("performance_policy_custody_invalid")
    _hex(custody["policy_sha256"])
    _hex(custody["required_baseline_observation_sha256"])
    _hex(custody["required_p1_locked_build_report_sha256"])

    expected_chain = {
        "twin_build": "identical",
        "static_layout": "layout_conformant",
        "composition_evidence_status": "incomplete",
        "archive_structural_admission": "conformant",
        "install_environment_class": "same_host_isolated_prefix",
        "performance_status": "observed_pending_owner_budget",
        "performance_threshold_verdict": "not_evaluated",
        "candidate_evaluation_status": "rejected",
        "promotion_status": "blocked",
        "release_candidate": False,
    }
    if document.get("chain_state") != expected_chain:
        raise ChainError("chain_state_invalid")
    blockers = document.get("global_blockers")
    if not isinstance(blockers, list) or len(blockers) != len(set(blockers)) or set(blockers) != REQUIRED_BLOCKERS:
        raise ChainError("global_blockers_invalid")
    gate_summary = document.get("gate_summary")
    if not isinstance(gate_summary, dict) or set(gate_summary) != {"observed_conformant_not_release", "observed_but_not_promotable", "rejected"} or gate_summary["rejected"] != ["candidate_evaluation_baseline_custody"]:
        raise ChainError("gate_summary_invalid")
    if document.get("promotion_status") != "blocked" or document.get("release_candidate") is not False:
        raise ChainError("promotion_state_invalid")
    non_claims = document.get("non_claims")
    if not isinstance(non_claims, list) or not non_claims or len(non_claims) != len(set(non_claims)) or any(not isinstance(item, str) or not item for item in non_claims):
        raise ChainError("non_claims_invalid")
    audit_ref = _safe_ref(document.get("audit_ref"))
    if not (ROOT / audit_ref).is_file():
        raise ChainError("audit_reference_unavailable")


def _external(path: Path) -> bool:
    resolved = path.resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def _read_external(path: Path, reason: str) -> bytes:
    if not _external(path):
        raise ChainError("external_evidence_required")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or before.st_size <= 0 or before.st_size > MAX_EXTERNAL_BYTES:
            raise ChainError(reason)
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise ChainError(reason) from error
    if before.st_size != len(raw) or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ChainError("external_evidence_changed_during_read")
    return raw


def _external_json(path: Path, reference: dict[str, object], reason: str) -> dict[str, Any]:
    raw = _read_external(path, reason)
    if sha256_bytes(raw) != reference["sha256"] or len(raw) != reference["bytes"]:
        raise ChainError(f"{reason}_identity_mismatch")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChainError(reason) from error
    if not isinstance(document, dict):
        raise ChainError(reason)
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
    evaluation_rejection_output: Path,
) -> None:
    evidence = document["evidence"]
    policy_raw = _read_external(layout_policy, "layout_policy_invalid")
    if sha256_bytes(policy_raw) != evidence["layout_policy"]["sha256"] or len(policy_raw) != evidence["layout_policy"]["bytes"]:
        raise ChainError("layout_policy_identity_mismatch")
    try:
        policy = json.loads(policy_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChainError("layout_policy_invalid") from error
    if not isinstance(policy, dict) or policy.get("schema") != "sipi.release-layout-policy.v1" or "bcryptprimitives.dll" not in policy.get("normalImportDllAllowlist", []):
        raise ChainError("layout_policy_invalid")

    twin_raw = _read_external(twin_report, "twin_report_invalid")
    twin = _external_json(twin_report, evidence["twin_report"], "twin_report")
    layout = _external_json(layout_report, evidence["layout_report"], "layout_report")
    composition = _external_json(composition_report, evidence["composition_report"], "composition_report")
    archive = _external_json(archive_report, evidence["archive_report"], "archive_report")
    install = _external_json(install_report, evidence["install_report"], "install_report")
    performance = _external_json(performance_observation, evidence["performance_observation"], "performance_observation")
    rejection_raw = _read_external(evaluation_rejection_output, "evaluation_rejection_output_invalid")
    if sha256_bytes(rejection_raw) != evidence["evaluation_rejection_output"]["sha256"] or len(rejection_raw) != evidence["evaluation_rejection_output"]["bytes"]:
        raise ChainError("evaluation_rejection_output_identity_mismatch")
    try:
        rejection = json.loads(rejection_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChainError("evaluation_rejection_output_invalid") from error
    if rejection != {"reason": "evidence_json_invalid", "schema": "sipi.p7-fixed-tran-candidate-performance-evaluation.v1", "status": "rejected"}:
        raise ChainError("evaluation_rejection_output_invalid")

    composition_gate = _load_module("p7_composition_for_current_chain", "verify_p7_release_composition.py")
    archive_gate = _load_module("p7_archive_for_current_chain", "verify_p7_release_archive.py")
    install_gate = _load_module("p7_install_for_current_chain", "verify_p7_isolated_install.py")
    measure = _load_module("p7_measure_for_current_chain", "measure_tran_rc_pulse_performance.py")
    try:
        twin_identity = composition_gate.parse_twin_report(twin)
        layout_identity = composition_gate.parse_layout_report(layout)
        composition_identity = archive_gate.parse_composition(composition)
        archive_identity = install_gate.parse_prior_report(archive)
        observation = measure.validate_observation(performance)
    except Exception as error:  # verifier modules expose distinct exception classes
        raise ChainError("current_chain_report_schema_invalid") from error
    if not observation.get("valid"):
        raise ChainError("performance_observation_invalid")
    candidate = document["candidate_executable"]
    if (
        twin_identity["commit"] != document["candidate_source_commit"]
        or twin_identity["tree"] != document["candidate_tree"]
        or twin_identity["lock_sha256"] != document["candidate_cargo_lock_sha256"]
        or twin_identity["toolchain_sha256"] != document["candidate_toolchain_sha256"]
        or twin_identity["binary_sha256"] != candidate["sha256"]
        or twin_identity["binary_bytes"] != candidate["bytes"]
    ):
        raise ChainError("twin_candidate_binding_invalid")
    if layout_identity["binary_sha256"] != candidate["sha256"] or layout_identity["binary_bytes"] != candidate["bytes"] or layout.get("policySha256") != evidence["layout_policy"]["sha256"]:
        raise ChainError("layout_candidate_binding_invalid")
    source = composition_identity
    if (
        source["commit"] != document["candidate_source_commit"]
        or source["tree"] != document["candidate_tree"]
        or source["cargo_lock_sha256"] != document["candidate_cargo_lock_sha256"]
        or source["toolchain_sha256"] != document["candidate_toolchain_sha256"]
        or source["staged_binary_sha256"] != candidate["sha256"]
        or source["staged_binary_bytes"] != candidate["bytes"]
        or source["twin_report_sha256"] != evidence["twin_report"]["sha256"]
        or source["evidence_status"] != "incomplete"
    ):
        raise ChainError("composition_candidate_binding_invalid")
    if (
        archive_identity["composition_report_sha256"] != evidence["composition_report"]["sha256"]
        or archive_identity["source_commit"] != document["candidate_source_commit"]
        or archive_identity["composition_evidence_status"] != "incomplete"
        or archive_identity["archive_sha256"] != document["stage_observations"]["archive"]["archive_sha256"]
        or archive_identity["archive_bytes"] != document["stage_observations"]["archive"]["archive_bytes"]
    ):
        raise ChainError("archive_candidate_binding_invalid")
    entries = archive_identity["entries"]
    main = [entry for entry in entries if isinstance(entry, dict) and entry.get("role") == "main_executable"]
    if len(main) != 1 or main[0].get("content_sha256") != candidate["sha256"] or main[0].get("bytes") != candidate["bytes"]:
        raise ChainError("archive_executable_binding_invalid")
    required_install = {"schema", "status", "environment_class", "fresh_machine", "fresh_user", "host_loader_closure", "promotion_status", "archive_sha256", "archive_report_sha256", "installed_executable_sha256", "sanitization_policy_sha256", "probes", "limitations"}
    if set(install) != required_install or install.get("status") != "isolated_install_smoke_passed" or install.get("environment_class") != "same_host_isolated_prefix" or install.get("fresh_machine") is not False or install.get("fresh_user") != "not_assessed" or install.get("host_loader_closure") != "not_assessed" or install.get("promotion_status") != "blocked" or install.get("archive_sha256") != archive_identity["archive_sha256"] or install.get("archive_report_sha256") != evidence["archive_report"]["sha256"] or install.get("installed_executable_sha256") != candidate["sha256"]:
        raise ChainError("install_candidate_binding_invalid")
    identity = performance.get("identity")
    if not isinstance(identity, dict) or identity.get("commit") != document["candidate_source_commit"] or identity.get("cargo_lock_sha256") != document["candidate_cargo_lock_sha256"] or identity.get("executable_sha256") != candidate["sha256"] or identity.get("executable_bytes") != candidate["bytes"]:
        raise ChainError("performance_candidate_binding_invalid")


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
    parser.add_argument("--evaluation-rejection-output", type=Path)
    arguments = parser.parse_args()
    try:
        document, raw = _load_json(arguments.document, "document_json_invalid")
        validate(document)
        external = (
            arguments.layout_policy,
            arguments.twin_report,
            arguments.layout_report,
            arguments.composition_report,
            arguments.archive_report,
            arguments.install_report,
            arguments.performance_observation,
            arguments.evaluation_rejection_output,
        )
        if any(path is not None for path in external):
            if any(path is None for path in external):
                raise ChainError("paired_external_evidence_required")
            verify_external_observation(document, **{
                "layout_policy": arguments.layout_policy,
                "twin_report": arguments.twin_report,
                "layout_report": arguments.layout_report,
                "composition_report": arguments.composition_report,
                "archive_report": arguments.archive_report,
                "install_report": arguments.install_report,
                "performance_observation": arguments.performance_observation,
                "evaluation_rejection_output": arguments.evaluation_rejection_output,
            })
        result = {"schema": SCHEMA, "valid": True, "document_sha256": sha256_bytes(raw)}
        print(json.dumps(result, sort_keys=True))
        return 0
    except ChainError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
