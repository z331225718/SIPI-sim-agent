"""Verify the hash-only P7 static-PE rejection diagnosis evidence."""

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
EVIDENCE = ROOT / "docs" / "baselines" / "p7-current-candidate-static-pe-rejection-diagnosis.v1.yaml"
PREFLIGHT_PATH = "docs/baselines/p7-current-candidate-chain-rebinding-preflight.v1.yaml"
OBSERVER_PATH = "tools/observe_p7_current_candidate_pe_rejection.py"
SCHEMA = "sipi.p7-current-candidate-static-pe-rejection-diagnosis.v1"
REPORT_SCHEMA = "sipi.p7-current-candidate-static-pe-rejection-observation.v1"
STATUS = "external_static_pe_rejection_diagnosed_current_candidate_chain_remains_blocked"
EXPECTED_ALLOWED_IMPORTS = [
    "api-ms-win-core-synch-l1-2-0.dll", "api-ms-win-crt-heap-l1-1-0.dll",
    "api-ms-win-crt-locale-l1-1-0.dll", "api-ms-win-crt-math-l1-1-0.dll",
    "api-ms-win-crt-runtime-l1-1-0.dll", "api-ms-win-crt-stdio-l1-1-0.dll",
    "kernel32.dll", "ntdll.dll", "vcruntime140.dll",
]
EXPECTED_NORMAL_IMPORTS = [*EXPECTED_ALLOWED_IMPORTS[:6], "bcryptprimitives.dll", *EXPECTED_ALLOWED_IMPORTS[6:]]


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


def external_regular(path: Path) -> bytes:
    resolved = path.resolve()
    if ROOT == resolved or ROOT in resolved.parents or not path.is_file() or path.is_symlink():
        raise EvidenceError("external_report_required")
    try:
        return path.read_bytes()
    except OSError as error:
        raise EvidenceError("external_report_required") from error


def git_text(*arguments: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True)
        return result.stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise EvidenceError("candidate_git_identity_invalid") from error


def product_inputs_match(commit: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--quiet", commit, "HEAD", "--", "Cargo.lock", "rust-toolchain.toml", "crates"],
            capture_output=True,
        )
    except OSError as error:
        raise EvidenceError("candidate_git_identity_invalid") from error
    if result.returncode not in (0, 1):
        raise EvidenceError("candidate_git_identity_invalid")
    return result.returncode == 0


def load_preflight() -> tuple[dict[str, Any], bytes]:
    path = ROOT / PREFLIGHT_PATH
    preflight, raw = load(path)
    spec = importlib.util.spec_from_file_location("p7_current_preflight", ROOT / "tools" / "verify_p7_current_candidate_chain_rebinding_preflight.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.validate(preflight)
    except module.PreflightError as error:
        raise EvidenceError("preflight_invalid") from error
    return preflight, raw


def expected_report(document: dict[str, Any]) -> dict[str, Any]:
    inputs = document["inputs"]
    observation = document["observation"]
    return {
        "schema": REPORT_SCHEMA,
        "status": STATUS,
        "fresh_materializations": inputs["fresh_materializations"],
        "policy": {"byte_length": 641, "sha256": inputs["policy_sha256"]},
        "executable": {"byte_length": inputs["executable_bytes"], "sha256": inputs["executable_sha256"]},
        "observation": {key: value for key, value in observation.items() if key != "canonical_observation_sha256"},
        "canonical_observation_sha256": observation["canonical_observation_sha256"],
        "non_claims": document["non_claims"],
    }


def validate(document: dict[str, Any], report_path: Path | None = None) -> dict[str, object]:
    expected_keys = {"schema", "status", "preflight", "candidate", "observer", "external_report", "inputs", "observation", "gates", "non_claims"}
    if set(document) != expected_keys or document.get("schema") != SCHEMA or document.get("status") != STATUS:
        raise EvidenceError("evidence_schema_invalid")
    preflight, preflight_raw = load_preflight()
    if document["preflight"] != {"path": PREFLIGHT_PATH, "sha256": sha256(preflight_raw)}:
        raise EvidenceError("preflight_binding_invalid")
    candidate = document["candidate"]
    if (
        not isinstance(candidate, dict)
        or set(candidate) != {"source_commit", "source_tree", "committed_product_inputs"}
        or candidate["source_commit"] != preflight["candidate_source_commit"]
        or candidate["source_tree"] != preflight["candidate_tree"]
        or candidate["committed_product_inputs"] != "unchanged_since_preflight"
    ):
        raise EvidenceError("candidate_binding_invalid")
    if not product_inputs_match(candidate["source_commit"]):
        raise EvidenceError("candidate_product_inputs_source_drift")
    observer = document["observer"]
    if (
        not isinstance(observer, dict)
        or set(observer) != {"path", "sha256"}
        or observer["path"] != OBSERVER_PATH
        or observer["sha256"] != sha256((ROOT / OBSERVER_PATH).read_bytes())
    ):
        raise EvidenceError("observer_binding_invalid")
    report = document["external_report"]
    if (
        not isinstance(report, dict)
        or set(report) != {"schema", "sha256", "byte_length", "custody"}
        or report["schema"] != REPORT_SCHEMA
        or report["custody"] != "operator_external_only"
        or not isinstance(report["byte_length"], int)
        or report["byte_length"] <= 0
    ):
        raise EvidenceError("external_report_binding_invalid")
    exact_hex(report["sha256"])
    inputs = document["inputs"]
    if (
        not isinstance(inputs, dict)
        or set(inputs) != {"fresh_materializations", "policy_sha256", "executable_sha256", "executable_bytes"}
        or inputs["fresh_materializations"] != 2
        or inputs["policy_sha256"] != preflight["static_layout"]["policy_sha256"]
        or inputs["executable_sha256"] != preflight["twin_build"]["binary_sha256"]
        or inputs["executable_bytes"] != preflight["twin_build"]["binary_bytes"]
    ):
        raise EvidenceError("input_binding_invalid")
    for key in ("policy_sha256", "executable_sha256"):
        exact_hex(inputs[key])
    observation = document["observation"]
    expected_observation_keys = {
        "pe_parse_status", "machine", "delay_import_directory_present", "normal_import_dlls",
        "allowed_import_dlls", "disallowed_import_dlls", "forbidden_token_import_dlls",
        "rejection_classification", "canonical_observation_sha256",
    }
    if (
        not isinstance(observation, dict)
        or set(observation) != expected_observation_keys
        or observation["pe_parse_status"] != "parsed"
        or observation["machine"] != "windows-x86_64"
        or observation["delay_import_directory_present"] is not False
        or observation["normal_import_dlls"] != EXPECTED_NORMAL_IMPORTS
        or observation["allowed_import_dlls"] != EXPECTED_ALLOWED_IMPORTS
        or observation["disallowed_import_dlls"] != ["bcryptprimitives.dll"]
        or observation["forbidden_token_import_dlls"] != []
        or observation["rejection_classification"] != "normal_import_disallowed"
        or not all(isinstance(value, list) and value == sorted(set(value)) for value in (observation["normal_import_dlls"], observation["allowed_import_dlls"], observation["disallowed_import_dlls"], observation["forbidden_token_import_dlls"]))
    ):
        raise EvidenceError("observation_invalid")
    exact_hex(observation["canonical_observation_sha256"])
    gates = document["gates"]
    expected_gates = {
        "layout_policy_changed": False, "allowlist_expanded": False,
        "static_or_dynamic_dependency_closure_evaluated": False, "composition_invoked": False,
        "archive_invoked": False, "install_invoked": False, "performance_observation_invoked": False,
        "candidate_evaluation_invoked": False, "current_candidate_p7_chain_admitted": False,
        "release_candidate": False, "promotion_status": "blocked",
    }
    if gates != expected_gates:
        raise EvidenceError("gate_state_invalid")
    expected_non_claims = [
        "not_a_layout_policy_change_or_allowlist_expansion", "not_static_or_dynamic_dependency_closure",
        "not_composition_archive_install_performance_or_candidate_evaluation", "not_release_readiness_or_promotion",
    ]
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
    return {"schema": SCHEMA, "valid": True, "report_bound": report_path is not None, "classification": observation["rejection_classification"]}


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
