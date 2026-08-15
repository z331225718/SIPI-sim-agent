"""Verify the hash-only P7 BCryptPrimitives/ProcessPrng preflight evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p7-bcryptprimitives-processprng-preflight.v1.yaml"
PREDECESSOR_PATH = "docs/baselines/p7-current-candidate-static-pe-rejection-diagnosis.v1.yaml"
OBSERVER_PATH = "tools/observe_p7_bcryptprimitives_processprng_preflight.py"
SCHEMA = "sipi.p7-bcryptprimitives-processprng-preflight.v1"
REPORT_SCHEMA = "sipi.p7-bcryptprimitives-processprng-preflight-observation.v1"
STATUS = "external_processprng_loader_api_ownership_preflight_observed_policy_revision_pending"


class EvidenceError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("evidence_unavailable") from error
    if not isinstance(document, dict):
        raise EvidenceError("evidence_schema_invalid")
    return document, raw


def exact_hex(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise EvidenceError("evidence_digest_invalid")
    return value


def git_text(*arguments: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True).stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise EvidenceError("candidate_git_identity_invalid") from error


def product_inputs_match(commit: str) -> bool:
    try:
        result = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", commit, "HEAD", "--", "Cargo.lock", "rust-toolchain.toml", "crates"], capture_output=True)
    except OSError as error:
        raise EvidenceError("candidate_git_identity_invalid") from error
    if result.returncode not in (0, 1):
        raise EvidenceError("candidate_git_identity_invalid")
    return result.returncode == 0


def external_regular(path: Path) -> bytes:
    resolved = path.resolve()
    if ROOT == resolved or ROOT in resolved.parents or not path.is_file() or path.is_symlink():
        raise EvidenceError("external_report_required")
    try:
        return path.read_bytes()
    except OSError as error:
        raise EvidenceError("external_report_required") from error


def expected_report(document: dict[str, Any]) -> dict[str, Any]:
    observation = document["observation"]
    return {
        "schema": REPORT_SCHEMA,
        "status": STATUS,
        "fresh_materializations": observation["fresh_materializations"],
        "executable": observation["executable"],
        "candidate_import_and_smoke": observation["candidate_import_and_smoke"],
        "authority": observation["authority"],
        "toolchain": observation["toolchain"],
        "same_host_system_dll": observation["same_host_system_dll"],
        "distribution": observation["distribution"],
        "gates": {
            "layout_policy_v2_implemented": False,
            "allowlist_expanded": False,
            "composition_invoked": False,
            "archive_invoked": False,
            "install_invoked": False,
            "performance_observation_invoked": False,
            "candidate_evaluation_invoked": False,
            "dynamic_runtime_closure_evaluated": False,
            "release_candidate": False,
            "promotion_status": "blocked",
        },
        "non_claims": [
            "not_a_layout_policy_revision", "not_cross_version_or_cross_device_loader_closure",
            "not_fresh_machine_or_security_review", "not_release_readiness_or_promotion",
        ],
    }


def validate(document: dict[str, Any], report_path: Path | None = None) -> dict[str, object]:
    expected_keys = {"schema", "status", "predecessor", "candidate", "observer", "external_report", "observation", "gates", "non_claims"}
    if set(document) != expected_keys or document.get("schema") != SCHEMA or document.get("status") != STATUS:
        raise EvidenceError("evidence_schema_invalid")
    predecessor, predecessor_raw = load(ROOT / PREDECESSOR_PATH)
    if document["predecessor"] != {"path": PREDECESSOR_PATH, "sha256": sha256(predecessor_raw)}:
        raise EvidenceError("predecessor_binding_invalid")
    candidate = document["candidate"]
    if (
        not isinstance(candidate, dict) or set(candidate) != {"source_commit", "source_tree", "committed_product_inputs"}
        or candidate["source_commit"] != predecessor["candidate"]["source_commit"]
        or candidate["source_tree"] != predecessor["candidate"]["source_tree"]
        or candidate["committed_product_inputs"] != "unchanged_since_static_pe_rejection_diagnosis"
        or git_text("rev-parse", candidate["source_commit"]) != candidate["source_commit"]
        or git_text("rev-parse", f"{candidate['source_commit']}^{{tree}}") != candidate["source_tree"]
        or not product_inputs_match(candidate["source_commit"])
    ):
        raise EvidenceError("candidate_binding_invalid")
    observer = document["observer"]
    if not isinstance(observer, dict) or observer != {"path": OBSERVER_PATH, "sha256": sha256((ROOT / OBSERVER_PATH).read_bytes())}:
        raise EvidenceError("observer_binding_invalid")
    report = document["external_report"]
    if not isinstance(report, dict) or set(report) != {"schema", "sha256", "byte_length", "custody"} or report["schema"] != REPORT_SCHEMA or report["custody"] != "operator_external_only" or not isinstance(report["byte_length"], int) or report["byte_length"] <= 0:
        raise EvidenceError("external_report_binding_invalid")
    exact_hex(report["sha256"])
    observation = document["observation"]
    expected_observation_keys = {"fresh_materializations", "executable", "candidate_import_and_smoke", "authority", "toolchain", "same_host_system_dll", "distribution"}
    if not isinstance(observation, dict) or set(observation) != expected_observation_keys or observation["fresh_materializations"] != 2 or observation["distribution"] != "provided_by_operating_system_not_packaged_or_redistributed":
        raise EvidenceError("observation_invalid")
    executable = observation["executable"]
    if executable != {"byte_length": predecessor["inputs"]["executable_bytes"], "sha256": predecessor["inputs"]["executable_sha256"]}:
        raise EvidenceError("executable_binding_invalid")
    imports = observation["candidate_import_and_smoke"]
    expected_import_keys = {"machine", "delay_import_directory_present", "bcryptprimitives_import", "normal_import_dlls", "system32_only_smoke"}
    if not isinstance(imports, dict) or set(imports) != expected_import_keys or imports["machine"] != "windows-x86_64" or imports["delay_import_directory_present"] is not False or imports["bcryptprimitives_import"] != {"import_kind": "name", "symbols": ["ProcessPrng"]} or imports["normal_import_dlls"] != predecessor["observation"]["normal_import_dlls"]:
        raise EvidenceError("processprng_import_observation_invalid")
    smoke = imports["system32_only_smoke"]
    if not isinstance(smoke, dict) or smoke.get("args") != ["version", "--json"] or smoke.get("exit_code") != 0 or smoke.get("stderr_bytes") != 0 or any(key not in smoke for key in ("stdout_sha256", "stderr_sha256", "stdout_bytes")):
        raise EvidenceError("same_host_smoke_invalid")
    authority = observation["authority"]
    if not isinstance(authority, dict) or set(authority) != {"process_prng", "rust_windows_msvc", "api_set_loader", "frozen_facts"} or authority["frozen_facts"] != {"process_prng_dll": "bcryptprimitives.dll", "process_prng_api_set": "CngRngExt", "process_prng_minimum_client": "windows_8_desktop", "process_prng_minimum_server": "windows_server_2008_r2_desktop", "rust_target_client_floor": "windows_10", "rust_target_server_floor": "windows_server_2016", "api_set_mapping_device_dependent": True}:
        raise EvidenceError("authority_observation_invalid")
    for key in ("process_prng", "rust_windows_msvc", "api_set_loader"):
        item = authority[key]
        if not isinstance(item, dict) or set(item) != {"url", "byte_length", "sha256"} or not isinstance(item["byte_length"], int) or item["byte_length"] <= 0:
            raise EvidenceError("authority_observation_invalid")
        exact_hex(item["sha256"])
    toolchain = observation["toolchain"]
    if not isinstance(toolchain, dict) or toolchain.get("release") != "1.97.0" or toolchain.get("host") != "x86_64-pc-windows-msvc" or toolchain.get("workspace_or_locked_third_party_processprng_package_declared") is not False or toolchain.get("ownership_assessment") != "toolchain_standard_library_linkage_supported_not_product_callsite_provenance" or not isinstance(toolchain.get("std_rlib"), dict) or toolchain["std_rlib"].get("processprng_tokens_present") is not True:
        raise EvidenceError("toolchain_observation_invalid")
    for value in (toolchain["version_sha256"], toolchain["std_rlib"].get("sha256")):
        exact_hex(value)
    system_dll = observation["same_host_system_dll"]
    if not isinstance(system_dll, dict) or system_dll.get("regular_system32_file") is not True or system_dll.get("signature_status") != "valid_microsoft_windows" or not isinstance(system_dll.get("byte_length"), int) or system_dll["byte_length"] <= 0:
        raise EvidenceError("same_host_dll_observation_invalid")
    exact_hex(system_dll.get("sha256"))
    expected_gates = {"layout_policy_v2_implemented": False, "allowlist_expanded": False, "static_or_dynamic_dependency_closure_evaluated": False, "composition_invoked": False, "archive_invoked": False, "install_invoked": False, "performance_observation_invoked": False, "candidate_evaluation_invoked": False, "current_candidate_p7_chain_admitted": False, "release_candidate": False, "promotion_status": "blocked"}
    if document["gates"] != expected_gates:
        raise EvidenceError("gate_state_invalid")
    expected_non_claims = ["not_a_layout_policy_revision_or_allowlist_expansion", "not_cross_version_or_cross_device_loader_closure", "not_fresh_machine_or_security_review", "not_release_readiness_or_promotion"]
    if document["non_claims"] != expected_non_claims:
        raise EvidenceError("non_claims_invalid")
    if report_path is not None:
        raw = external_regular(report_path)
        if sha256(raw) != report["sha256"] or len(raw) != report["byte_length"]:
            raise EvidenceError("external_report_identity_drift")
        try:
            observed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvidenceError("external_report_invalid") from error
        if observed != expected_report(document):
            raise EvidenceError("external_report_content_invalid")
    return {"schema": SCHEMA, "valid": True, "report_bound": report_path is not None, "policy_revision_pending": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        document, _ = load(arguments.evidence)
        print(json.dumps(validate(document, arguments.report), sort_keys=True))
        return 0
    except (EvidenceError, OSError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
