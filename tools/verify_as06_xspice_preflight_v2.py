"""Verify the immutable, blocked AS-06 XSPICE build preflight observation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.as-06-xspice-rfm-build-preflight.v2"
MANIFEST_SCHEMA = SCHEMA + ".manifest"
AUDIT_SCHEMA = SCHEMA + ".audit"
REPORT_REL = "docs/baselines/as-06-xspice-rfm-build-preflight-v2.json"
MANIFEST_REL = "docs/baselines/as-06-xspice-rfm-build-preflight-v2.manifest.json"
AUDIT_REL = "docs/baselines/audits/2026-08-24-as-06-xspice-rfm-build-preflight-v2.json"
VERIFIER_REL = "tools/verify_as06_xspice_preflight_v2.py"
MUTATION_REL = "tools/test_verify_as06_xspice_preflight_v2.py"
REPORT_SHA = "e7f5dc054bade2802b97dad27995de8d5b71ef22322f5836c3bc3a416209eecb"
RUN_ID = "as06-preflight-v2-20260824-01"
NONCE = "923cf9950bfb531bbd7f72becb6a4e93cc2e901cd0fe2ac687d409e88f17625d"
CANDIDATE = {
    "commit": "d3b53057d9751b8edf427bbe74cd34f7e4ed02f7",
    "tree": "bc297933a116f7a326d144295ca15bc487126fce",
    "archive_sha256": "6813a94d4bb6cfa2736426a79619ed0aacad6464a5592da06fee841a8440e37c",
    "archive_bytes": 44349440,
}
UPSTREAM = {
    "commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5",
    "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402",
    "archive_sha256": "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144",
}
RUNNER_SHA = "f9553dff0c1a1353e09b2fd16f6e83dba5e9261c15868bb96ca4f1b1a5ab0e89"
RUNNER_BYTES = 29061
WORKTREE_RUNNER_SHA = "7a3588f71a9e5516d68297714f4da037c45b56fe2badb974872a06b70c463ddc"
WORKTREE_RUNNER_BYTES = 28498
TOOLCHAIN_SHA = "814e784fde7a05752f708d5850a1d254f2f5805e26a1eac71244d24fee8ea0ac"
CLOSURE_SHA = "22ae5eb9c4001d15b62fa2fd3b4d52ea702b72956a2c6f4e1e0728ef1954a7fa"
SOURCES_SHA = "94f101fa5b8f8c0686520e645b2ca19a827e02783ae75383e88dea474ec7c6e4"
DOCKER_SHA = "4f74c75e49a116e86902b00b3448e4a053093c11df5dfd87cff507059e2e2dbd"
ASSET_SHA = "7e9f4b42378fda6446c903be14db3fdfbac4e4ec2a7eb00cef6ca3c6f747e884"
BLOCKERS = ["source_asset_missing", "docker_info_failed"]
NON_CLAIMS = [
    "no_code_model_built",
    "no_ngspice_replay",
    "no_numeric_parity",
    "no_as06_row_closure",
    "no_release_promotion",
]
SCOPE = {
    "build_attempted": False,
    "artifact_present": False,
    "workflow_not_run": True,
    "parity": False,
    "as06_row_closed": False,
    "release": False,
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class VerificationError(ValueError):
    pass


def fail(message: str) -> None:
    raise VerificationError(message)


def exact_keys(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        fail(f"{label} schema")


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"cannot load {path}: {exc}")


def path_free(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            path_free(item)
    elif isinstance(value, list):
        for item in value:
            path_free(item)
    elif isinstance(value, str):
        if re.search(r"(?:^[A-Za-z]:[\\/]|^\\\\|^/|/Users/|/home/|\\Users\\)", value):
            fail("absolute path disclosure")


def finite_numbers(value: Any, key: str = "") -> None:
    if isinstance(value, dict):
        for name, item in value.items():
            finite_numbers(item, name)
    elif isinstance(value, list):
        for item in value:
            finite_numbers(item, key)
    elif type(value) is float and not math.isfinite(value):
        fail("non-finite number")
    elif value is not None and key.endswith(("bytes", "exit_code", "returncode", "file_count", "entry_count", "total_bytes")) and type(value) is not int:
        fail("integer field is not an integer")


def identity_check(value: Any, label: str) -> None:
    keys = {
        "basename", "file_bytes", "file_sha256", "path_redacted", "version_exit_code",
        "version_output_bytes", "version_output_sha256", "version_overflow", "version_timeout",
    }
    if label.startswith("python"):
        keys.add("runtime_version_sha256")
    if label == "tarfile":
        keys = {"basename", "file_bytes", "file_sha256", "module_version", "path_redacted"}
    exact_keys(value, keys, label)
    if not isinstance(value.get("basename"), str) or "/" in value["basename"] or "\\" in value["basename"]:
        fail(f"{label} basename")
    for key in ("file_sha256", "version_output_sha256"):
        if key in value and (not isinstance(value[key], str) or not HEX64.fullmatch(value[key])):
            fail(f"{label} hash")
    for key in ("file_bytes", "version_output_bytes", "version_exit_code"):
        if key in value and type(value[key]) is not int or key in value and value[key] < 0:
            fail(f"{label} integer")
    if value.get("path_redacted") is not True:
        fail(f"{label} path policy")


def validate_report(report: Any) -> None:
    exact_keys(
        report,
        {"blockers", "build", "candidate", "closure", "docker", "non_claims", "os_nonce", "ready_to_build", "run_id", "runner", "schema", "source_asset", "sources", "status", "toolchain", "upstream"},
        "report",
    )
    path_free(report)
    finite_numbers(report)
    if report["schema"] != SCHEMA or report["status"] != "blocked_external_build_preflight":
        fail("report status")
    if report["run_id"] != RUN_ID or report["os_nonce"] != NONCE or report["ready_to_build"] is not False:
        fail("run identity")
    if report["blockers"] != BLOCKERS or report["non_claims"] != NON_CLAIMS:
        fail("blockers or non-claims")
    exact_keys(report["build"], {"artifact_present", "attempted"}, "build")
    if report["build"] != {"artifact_present": False, "attempted": False}:
        fail("build claim")
    exact_keys(report["candidate"], {"archive_observation", "archive_sha256", "commit", "materialization", "observed_commit", "observed_tree", "overlay_current_worktree", "runner_member", "tree"}, "candidate")
    if {k: report["candidate"][k] for k in ("commit", "tree", "archive_sha256")} != {"commit": CANDIDATE["commit"], "tree": CANDIDATE["tree"], "archive_sha256": CANDIDATE["archive_sha256"]}:
        fail("candidate anchor")
    if report["candidate"]["observed_commit"] != CANDIDATE["commit"] or report["candidate"]["observed_tree"] != CANDIDATE["tree"] or report["candidate"]["materialization"] != "candidate_clean_git_archive" or report["candidate"]["overlay_current_worktree"] is not False:
        fail("candidate observation")
    archive_observation = report["candidate"]["archive_observation"]
    exact_keys(archive_observation, {"bytes", "extract_status", "extracted", "overflow", "returncode", "sha256", "timeout"}, "candidate archive observation")
    if archive_observation["sha256"] != CANDIDATE["archive_sha256"] or archive_observation["bytes"] != CANDIDATE["archive_bytes"] or archive_observation["returncode"] != 0 or archive_observation["timeout"] is not False or archive_observation["overflow"] is not False or archive_observation["extracted"] is not True or archive_observation["extract_status"] != "ok":
        fail("candidate archive observation")
    exact_keys(report["candidate"]["runner_member"], {"match", "member_bytes", "member_overflow", "member_sha256", "path_redacted", "present", "runtime_bytes", "runtime_overflow", "runtime_sha256"}, "runner member")
    runner = report["candidate"]["runner_member"]
    if runner["match"] is not True or runner["present"] is not True or runner["path_redacted"] is not True or runner["member_overflow"] is not False or runner["runtime_overflow"] is not False or runner["member_sha256"] != RUNNER_SHA or runner["runtime_sha256"] != RUNNER_SHA or runner["member_bytes"] != RUNNER_BYTES or runner["runtime_bytes"] != RUNNER_BYTES:
        fail("runner archive custody")
    exact_keys(report["upstream"], {"archive_observation", "archive_sha256", "commit", "materialization", "observed_commit", "observed_tree", "tree"}, "upstream")
    upstream_observation = report["upstream"]["archive_observation"]
    exact_keys(upstream_observation, {"bytes", "extract_status", "extracted", "overflow", "returncode", "sha256", "timeout"}, "upstream archive observation")
    if report["upstream"]["commit"] != UPSTREAM["commit"] or report["upstream"]["tree"] != UPSTREAM["tree"] or report["upstream"]["archive_sha256"] != UPSTREAM["archive_sha256"] or report["upstream"]["observed_commit"] != UPSTREAM["commit"] or report["upstream"]["observed_tree"] != UPSTREAM["tree"] or report["upstream"]["materialization"] != "upstream_clean_git_archive" or upstream_observation["sha256"] != UPSTREAM["archive_sha256"] or upstream_observation["returncode"] != 0 or upstream_observation["timeout"] is not False or upstream_observation["overflow"] is not False or upstream_observation["extracted"] is not True or upstream_observation["extract_status"] != "ok":
        fail("upstream anchor")
    asset = report["source_asset"]
    if canonical_sha(asset) != ASSET_SHA or asset["kind"] != "missing" or asset["present"] is not False or asset["basename"] != "ngspice-46.tar.gz" or asset["expected_sha256"] != "a0d1699af1940b06649276dcd6ff5a566c8c0cad01b2f7b5e99dedbb4d64c19b":
        fail("asset observation")
    if canonical_sha(report["sources"]) != SOURCES_SHA or canonical_sha(report["closure"]) != CLOSURE_SHA or canonical_sha(report["docker"]) != DOCKER_SHA or canonical_sha(report["toolchain"]) != TOOLCHAIN_SHA:
        fail("external observation digest")
    exact_keys(report["runner"], {"archive_member", "initial", "path_redacted", "post", "runtime"}, "runner")
    for name in ("archive_member", "initial", "post", "runtime"):
        item = report["runner"][name]
        exact_keys(item, {"bytes", "overflow", "sha256"}, f"runner {name}")
        if item["bytes"] != RUNNER_BYTES or item["sha256"] != RUNNER_SHA or item["overflow"] is not False:
            fail("runner identity drift")
    if report["runner"]["path_redacted"] is not True:
        fail("runner path policy")
    for name, item in report["toolchain"].items():
        identity_check(item, name)
    exact_keys(report["docker"], {"exit_code", "output_bytes", "output_sha256", "path_redacted", "status", "timeout"}, "docker")
    if report["docker"]["status"] != "docker_info_failed" or report["docker"]["exit_code"] != 1 or report["docker"]["timeout"] is not False:
        fail("docker blocker")


def validate_manifest(manifest: Any, report: Any, audit: Any | None = None, physical: bool = False) -> None:
    exact_keys(manifest, {"audit", "blockers", "candidate", "closure_sha256", "docker_sha256", "manifest_policy", "mutation_tests", "non_claims", "report", "runner", "schema", "scope", "source_asset_sha256", "source_asset_observation_sha256", "sources_sha256", "status", "toolchain_sha256", "upstream", "verifier"}, "manifest")
    if manifest["schema"] != MANIFEST_SCHEMA or manifest["status"] != report["status"] or manifest["scope"] != SCOPE or manifest["blockers"] != BLOCKERS or manifest["non_claims"] != NON_CLAIMS:
        fail("manifest policy")
    if manifest["manifest_policy"] != {"external_solver": "not_observed", "promotion": "forbidden", "path_policy": "redacted", "environment_injection": "not_fully_excluded"}:
        fail("manifest policy detail")
    if manifest["candidate"] != {**CANDIDATE, "materialization": "candidate_clean_git_archive"} or manifest["upstream"] != {**UPSTREAM, "materialization": "upstream_clean_git_archive"}:
        fail("manifest provenance")
    if manifest["report"] != {"path": REPORT_REL, "sha256": REPORT_SHA, "run_id": RUN_ID, "os_nonce": NONCE}:
        fail("manifest report link")
    if manifest["runner"] != {"path": "tools/preflight_as06_xspice_rfm.py", "sha256": RUNNER_SHA, "archive_sha256": CANDIDATE["archive_sha256"], "materialization": "candidate_archive_member_core_autocrlf_true", "working_tree_sha256": WORKTREE_RUNNER_SHA, "working_tree_bytes": WORKTREE_RUNNER_BYTES}:
        fail("manifest runner link")
    if manifest["toolchain_sha256"] != TOOLCHAIN_SHA or manifest["source_asset_sha256"] is not None or manifest["source_asset_observation_sha256"] != ASSET_SHA or manifest["closure_sha256"] != CLOSURE_SHA or manifest["sources_sha256"] != SOURCES_SHA or manifest["docker_sha256"] != DOCKER_SHA:
        fail("manifest external links")
    for link, expected in (("verifier", VERIFIER_REL), ("mutation_tests", MUTATION_REL), ("audit", AUDIT_REL)):
        exact_keys(manifest[link], {"path", "sha256"}, link)
        if manifest[link]["path"] != expected or not HEX64.fullmatch(manifest[link]["sha256"]):
            fail(f"manifest {link} link")
    if physical:
        for link in ("verifier", "mutation_tests", "audit"):
            target = ROOT / manifest[link]["path"]
            if file_sha(target) != manifest[link]["sha256"]:
                fail(f"{link} hash")
        if file_sha(ROOT / REPORT_REL) != REPORT_SHA:
            fail("report hash")
        runner_source = ROOT / "tools/preflight_as06_xspice_rfm.py"
        if runner_source.stat().st_size != WORKTREE_RUNNER_BYTES or file_sha(runner_source) != WORKTREE_RUNNER_SHA:
            fail("runner physical source relation")
    if report["run_id"] != manifest["report"]["run_id"] or report["os_nonce"] != manifest["report"]["os_nonce"]:
        fail("report cross-link")
    if audit is not None:
        if manifest["audit"] != {"path": AUDIT_REL, "sha256": manifest["audit"]["sha256"]}:
            fail("audit link")


def validate_audit(audit: Any, manifest: Any, report: Any) -> None:
    exact_keys(audit, {"audit_policy", "blockers", "candidate", "closure_sha256", "docker_sha256", "mutation_tests", "non_claims", "report", "runner", "schema", "scope", "source_asset_sha256", "sources_sha256", "status", "toolchain_sha256", "upstream", "verifier"}, "audit")
    if audit["schema"] != AUDIT_SCHEMA or audit["status"] != manifest["status"] or audit["scope"] != SCOPE or audit["blockers"] != BLOCKERS or audit["non_claims"] != NON_CLAIMS:
        fail("audit policy")
    if audit["audit_policy"] != {"claim": "blocked_preflight_only", "parity": "not_claimed", "release": "not_promoted"}:
        fail("audit policy detail")
    if audit["candidate"] != manifest["candidate"] or audit["upstream"] != manifest["upstream"] or audit["report"] != manifest["report"] or audit["runner"] != manifest["runner"]:
        fail("audit provenance")
    if audit["source_asset_sha256"] is not None or manifest["source_asset_sha256"] is not None or audit["source_asset_sha256"] != report["source_asset"]["sha256"]:
        fail("audit source asset cross-link")
    for key in ("toolchain_sha256", "closure_sha256", "sources_sha256", "docker_sha256"):
        if audit[key] != manifest[key]:
            fail("audit external link")
    if audit["verifier"] != manifest["verifier"] or audit["mutation_tests"] != manifest["mutation_tests"]:
        fail("audit gate link")


def verify_data(report: Any, manifest: Any, audit: Any, physical: bool = False) -> None:
    validate_report(report)
    validate_manifest(manifest, report, audit, physical)
    validate_audit(audit, manifest, report)
    path_free(manifest)
    path_free(audit)


def verify_bundle(report_path: Path, manifest_path: Path, audit_path: Path) -> None:
    if report_path.as_posix() != (ROOT / REPORT_REL).as_posix() or manifest_path.as_posix() != (ROOT / MANIFEST_REL).as_posix() or audit_path.as_posix() != (ROOT / AUDIT_REL).as_posix():
        fail("unexpected evidence path")
    report = load(report_path)
    manifest = load(manifest_path)
    audit = load(audit_path)
    if file_sha(report_path) != REPORT_SHA:
        fail("report content hash")
    verify_data(report, manifest, audit, physical=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ROOT / REPORT_REL)
    parser.add_argument("--manifest", type=Path, default=ROOT / MANIFEST_REL)
    parser.add_argument("--audit", type=Path, default=ROOT / AUDIT_REL)
    args = parser.parse_args()
    try:
        verify_bundle(args.report.resolve(), args.manifest.resolve(), args.audit.resolve())
    except VerificationError as exc:
        print(f"blocked: {exc}")
        return 1
    print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
