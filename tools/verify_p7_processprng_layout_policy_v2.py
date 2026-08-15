"""Verify the additive, ProcessPrng-only P7 layout policy revision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p7-processprng-layout-policy.v2.yaml"
PREFLIGHT_PATH = "docs/baselines/p7-bcryptprimitives-processprng-preflight.v1.yaml"
SCHEMA = "sipi.p7-processprng-layout-policy.v2"
STATUS = "selected_windows10_server2016_desktop_layout_policy_defined_current_layout_observed_downstream_chain_pending"
POLICY = {
    "schema": "sipi.release-layout-policy.v1", "platform": "windows-x86_64", "expectedExecutable": "sipi.exe",
    "requiredFiles": ["sipi.exe", "LICENSE"], "optionalFiles": [],
    "normalImportDllAllowlist": [
        "api-ms-win-core-synch-l1-2-0.dll", "api-ms-win-crt-heap-l1-1-0.dll",
        "api-ms-win-crt-locale-l1-1-0.dll", "api-ms-win-crt-math-l1-1-0.dll",
        "api-ms-win-crt-runtime-l1-1-0.dll", "api-ms-win-crt-stdio-l1-1-0.dll",
        "bcryptprimitives.dll", "kernel32.dll", "ntdll.dll", "vcruntime140.dll",
    ],
    "forbiddenImportDllTokens": ["python", "pyami", "agent-spice"],
    "smoke": [{"args": ["version", "--json"]}, {"args": ["capabilities", "--json"]}, {"args": ["doctor", "--json"]}, {"args": ["schema", "list", "--json"]}],
}


class PolicyError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_policy() -> bytes:
    return json.dumps(POLICY, separators=(",", ":")).encode("utf-8") + b"\n"


def load(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PolicyError("evidence_unavailable") from error
    if not isinstance(value, dict):
        raise PolicyError("evidence_schema_invalid")
    return value, raw


def git_text(*arguments: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True).stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise PolicyError("candidate_identity_invalid") from error


def current_product_inputs(commit: str) -> bool:
    result = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", commit, "HEAD", "--", "Cargo.lock", "rust-toolchain.toml", "crates"], capture_output=True)
    if result.returncode not in (0, 1):
        raise PolicyError("candidate_identity_invalid")
    return result.returncode == 0


def external_regular(path: Path) -> bytes:
    resolved = path.resolve()
    if ROOT == resolved or ROOT in resolved.parents or not path.is_file() or path.is_symlink():
        raise PolicyError("external_layout_report_required")
    return path.read_bytes()


def validate(document: dict[str, Any], report_path: Path | None = None) -> dict[str, object]:
    expected_keys = {"schema", "status", "authority", "preflight", "candidate", "selected_platform_boundary", "policy", "external_layout_observation", "gates", "non_claims"}
    if set(document) != expected_keys or document.get("schema") != SCHEMA or document.get("status") != STATUS or document.get("authority") != "user_delegated_owner_discretion":
        raise PolicyError("evidence_schema_invalid")
    _, preflight_raw = load(ROOT / PREFLIGHT_PATH)
    if document["preflight"] != {"path": PREFLIGHT_PATH, "sha256": sha256(preflight_raw)}:
        raise PolicyError("preflight_binding_invalid")
    candidate = document["candidate"]
    if not isinstance(candidate, dict) or candidate != {"source_commit": "b775dde6d242e687eb71a30b9a83a87d8b31ba55", "source_tree": "35be864a88573709c2b316e063bfe90eb54678e2", "committed_product_inputs": "unchanged_since_processprng_preflight"} or git_text("rev-parse", candidate["source_commit"]) != candidate["source_commit"] or git_text("rev-parse", f"{candidate['source_commit']}^{{tree}}") != candidate["source_tree"] or not current_product_inputs(candidate["source_commit"]):
        raise PolicyError("candidate_binding_invalid")
    if document["selected_platform_boundary"] != {"target": "x86_64-pc-windows-msvc", "minimum_supported_desktop": "windows_10_or_windows_server_2016", "physical_dll_name_not_cross_device_api_set_policy": True}:
        raise PolicyError("platform_boundary_invalid")
    policy = document["policy"]
    expected_policy = {
        "schema": "sipi.release-layout-policy.v1", "required_files": ["sipi.exe", "LICENSE"],
        "normal_import_dll_allowlist": POLICY["normalImportDllAllowlist"],
        "delta_from_v1": {"added_normal_import_dll": "bcryptprimitives.dll", "removed_normal_import_dlls": []},
        "forbidden_import_dll_tokens": POLICY["forbiddenImportDllTokens"],
        "smoke_commands": [entry["args"] for entry in POLICY["smoke"]],
        "canonical_json_byte_length": len(canonical_policy()), "canonical_json_sha256": sha256(canonical_policy()),
    }
    if policy != expected_policy:
        raise PolicyError("policy_definition_invalid")
    observation = document["external_layout_observation"]
    if not isinstance(observation, dict) or set(observation) != {"schema", "sha256", "byte_length", "custody", "status"} or observation["schema"] != "sipi.release-layout-report.v1" or observation["custody"] != "operator_external_only" or observation["status"] != "layout_conformant" or not isinstance(observation["byte_length"], int) or observation["byte_length"] <= 0:
        raise PolicyError("layout_observation_binding_invalid")
    expected_gates = {"layout_policy_v2_defined": True, "allowlist_expanded_only_for_processprng": True, "static_dependency_closure_evaluated": False, "dynamic_runtime_closure_evaluated": False, "composition_invoked": False, "archive_invoked": False, "install_invoked": False, "performance_observation_invoked": False, "candidate_evaluation_invoked": False, "release_candidate": False, "promotion_status": "blocked"}
    if document["gates"] != expected_gates:
        raise PolicyError("gate_state_invalid")
    if document["non_claims"] != ["not_cross_version_or_cross_device_loader_closure", "not_a_static_or_dynamic_dependency_closure", "not_a_product_callsite_provenance_or_security_review", "not_a_fresh_machine_or_release_readiness_claim"]:
        raise PolicyError("non_claims_invalid")
    if report_path is not None:
        raw = external_regular(report_path)
        if sha256(raw) != observation["sha256"] or len(raw) != observation["byte_length"]:
            raise PolicyError("external_layout_report_identity_drift")
        try:
            report = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PolicyError("external_layout_report_invalid") from error
        expected_report = {
            "schema": "sipi.release-layout-report.v1", "status": "layout_conformant",
            "policySha256": sha256(canonical_policy()),
            "inventorySha256": "6be163cde5ba9b3906e7982ce657b234f2b19294638b053c191e5db08ef45812",
            "executableSha256": "a3059d052df54c0f3ebbd727bd2f71760ff33f73af82e1e2f29c0ec35b8c882d",
            "executableBytes": 3908608, "machine": "amd64",
            "normalImports": POLICY["normalImportDllAllowlist"], "delayImportDirectoryPresent": False,
            "smoke": [
                {"args": ["version", "--json"], "exitCode": 0, "stdoutSha256": "fd5ca3a9c17338be055b18c37d5ede95d88e929172d2cade97888504e9d68663", "stderrSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
                {"args": ["capabilities", "--json"], "exitCode": 0, "stdoutSha256": "46fb24ae991ccb424190bd290c37463b78ed2d436adcb4d2e8a69e8936ea47b8", "stderrSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
                {"args": ["doctor", "--json"], "exitCode": 0, "stdoutSha256": "eac21c81bd526242e0ade57a1d5d4c449e9d59c970ef46c656929f0fb8284a49", "stderrSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
                {"args": ["schema", "list", "--json"], "exitCode": 0, "stdoutSha256": "c3e6e6cf3f54948005bb2a6798ae27bc61594d400196f795753e605dc08b634b", "stderrSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
            ],
            "limitations": [
                "provisional product boundary; this is not release readiness",
                "no hostile-filesystem containment claim",
                "no arbitrary-command child-process or dynamic-load claim",
            ],
        }
        if report != expected_report:
            raise PolicyError("external_layout_report_content_invalid")
    return {"schema": SCHEMA, "valid": True, "layout_report_bound": report_path is not None, "downstream_chain_pending": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        document, _ = load(arguments.evidence)
        print(json.dumps(validate(document, arguments.report), sort_keys=True))
        return 0
    except (PolicyError, OSError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
