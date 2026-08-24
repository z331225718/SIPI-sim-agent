"""Strict verifier for the additive PB-01 scoped observation inventory."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/baselines/pb-01-03-branch-inventory-ab1fc.v1.yaml"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_CANDIDATE = {
    "commit": "ab1fc77024383ab6dafed3df96babced420c830d",
    "tree": "bcf1e8a7c99681074c55d0c96cb7eca88a9c7f4b",
    "archive_sha256": "bd3e7a5588d9d3ebadb22a0f90f639e3598c5e102bdf0eca24b2d1bc787b5745",
    "archive_bytes": 43796480,
}
EXPECTED_UPSTREAM = {
    "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
    "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
}
REPORTS = (
    "docs/baselines/pb-01-legacy-leaf-ab1fc-current-run-01.json",
    "docs/baselines/pb-01-legacy-leaf-ab1fc-current-run-02.json",
)
AGGREGATE = "docs/baselines/pb-01-legacy-leaf-ab1fc-current-aggregate.json"
AUDIT = "docs/baselines/audits/2026-08-24-pb-01-03-ab1fc-branch-inventory.md"
AGGREGATOR = "tools/aggregate_pb_01_legacy_leaf_replay.py"
EXPECTED_REPORT_SHA = (
    "4878faa5d9f91896fd38de36db116889a3048d7e9f3fa467005f16591709cc32",
    "f077639e1d387580884f02c2868106591f61896033fb06a7053329baee9eeeee",
)
EXPECTED_AGGREGATE_SHA = "60c624abcb36a4d5cd1ffbac65aab1b95771ed04fc22d72bbe11365e53ffea6a"
EXPECTED_AUDIT_SHA = "ce8fc2bd1c3a1b84f8454ec9f41e126b1fd8aa17a5b139a329b23b2cf2d046fa"
EXPECTED_AGGREGATOR_SHA = "c3454cfa62b1669ec1b94e55e9aab175ea90023d22dc85c383fc72261d489e79"
EXPECTED_STRUCTURE_SHA = {
    "claims": "c6fb6f0c7b7423d6d12c11813bfdc172be45e9209efcaa6a1fe0eecc064954ba",
    "replay_policy": "757c906e4cab0667889644ea3f08599752cae83dd3091d04794708860fcb14f9",
    "rows": "1d76df6d8acda49d3be4be2d307739988805b802f941cb93c9478c6b3dfed721",
    "cases": "0cfc01d792f667daf4b49c68d32b1670e634281ed1e22366891c410c0fad1cc9",
    "source_scope": "42860c88ceed04eab584c0e9d7f3bd8bdea99842839d478a66b63081275a7fda",
    "non_claims": "de234646bb1f9606cdcdbc12bddaea88dcf323f912d3df551ec61df6e0841803",
    "upstream": "381fa1e149d8cb0b7d1d896e4464f998450f81d44764695753d2edb60e379483",
}
EXPECTED_REPORT_RUNS = (("pb01-ab1-run-01", "2745afa0c752aebec2f50823dae8ec9b37447cba60664c52fee1b1b89a654261"), ("pb01-ab1-run-02", "93b4914ab0ecdb5650eb5c2ae88d1d17b745bd44a4686224194ec10a6b079aa6"))
EXPECTED_CANDIDATE_SOURCE_SHA = {
    "crates/sipi-pybert-direct/src/input.rs": "25a0af0d0442f9d96e1488518404254ea058468b48b8294e13afcc878a3f1947",
    "crates/sipi-pybert-direct/src/simulation.rs": "66390a482f00914bdf2ce92f2a274818eb2f6bd26f5b0b9bc22705cf7a3428a5",
    "crates/sipi-pybert-direct/src/legacy_runtime.rs": "9e16c4a9ae421e8cfeed55651a92ffaee13461f9d3847c9a4b16a72d19f43e02",
    "crates/sipi-pybert-direct/src/external_host.rs": "4d7d87e59d714c2cc13cf9285e1bada68ce5006c052e0496ce46a40c5f4bf572",
    "crates/sipi-pybert-direct/tests/native_branch_matrix.rs": "aeba651902ba002c71661d7ceec9507be7bfa2db3ec7fce3804d86e7e366fef5",
    "crates/sipi-pybert-direct/tests/legacy_runtime.rs": "decc6bda4cec80a8bace9455c72e8da2cd73a0e840934135937909f2e1938ff7",
}
EXPECTED_UPSTREAM_BLOBS = {
    "src/pybert/cli.py": "4c1116007d31bcebf8db3252363eed7774c7b349",
    "src/pybert/configuration.py": "ef24ded89768291e7b5e945fab4fe50be3bd6c2d",
    "src/pybert/pybert.py": "1af665c4595fff1ff5fb30341fe063bd10e5cd89",
    "src/pybert/results.py": "4d8eafa77a20ef8a3ac307f6ae8c0397deb8e907",
    "src/pybert/engine/python_backend.py": "6b7b664d89da1502c74fc7cd97fe4451bf98ab82",
}
HARNESS = {
    "tools/run_pb_01_legacy_leaf_replay.py": "4632a402962b24bdc1cd2c2869c728d58f1dc9afe6e9372e6b4499203033bd87",
    "tools/run_pb_02_direct_replay.py": "ccae9d8266912cc4b00174c39ed6ef8ac06cd5a31667c3f44d77c6cf4be5782e",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _git_blob(repo: Path, revision: str, path: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), "rev-parse", f"{revision}:{path}"], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_archive_identity(repo: Path, revision: str) -> tuple[int, str]:
    result = subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(repo), "archive", "--format=tar", revision], capture_output=True, check=False)
    return len(result.stdout), hashlib.sha256(result.stdout).hexdigest() if result.returncode == 0 else ""


def _safe(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("path is not a non-empty repository-relative string")
    posix, windows = PurePosixPath(relative), PureWindowsPath(relative)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts:
        raise ValueError("absolute or traversal path")
    path = root / Path(*posix.parts)
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("path escapes repository root")
    return path


def _walk_paths(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "fixture", "aggregate_path", "audit_path", "source_map"} and isinstance(item, str):
                paths.append(item)
            paths.extend(_walk_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_walk_paths(item))
    return paths


def verify_inventory(root: Path = ROOT, inventory_path: Path = INVENTORY) -> dict[str, Any]:
    blockers: list[str] = []
    inventory = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(inventory, dict):
        return {"status": "blocked", "blockers": ["inventory is not a mapping"]}
    expected_keys = {"schema", "status", "claims", "candidate", "upstream", "replay_policy", "rows", "cases", "source_scope", "audit", "non_claims"}
    if set(inventory) != expected_keys:
        blockers.append("inventory top-level schema drift")
    for path in _walk_paths(inventory):
        try:
            _safe(root, path)
        except ValueError:
            blockers.append(f"unsafe path: {path}")
    if inventory.get("schema") != "sipi.pb-01-03-branch-inventory.v1":
        blockers.append("inventory schema mismatch")
    if inventory.get("status") != "scoped_environment_local_numeric_observation":
        blockers.append("inventory must remain an environment-local observation")
    for key, expected in EXPECTED_STRUCTURE_SHA.items():
        if _canonical_sha(inventory.get(key)) != expected:
            blockers.append(f"{key} exact structure drift")
    if inventory.get("candidate") != EXPECTED_CANDIDATE:
        blockers.append("candidate identity drift")
    upstream = inventory.get("upstream")
    if not isinstance(upstream, dict) or {key: upstream.get(key) for key in EXPECTED_UPSTREAM} != EXPECTED_UPSTREAM:
        blockers.append("upstream identity drift")
    candidate_archive_bytes, candidate_archive_sha = _git_archive_identity(ROOT, EXPECTED_CANDIDATE["commit"])
    if (candidate_archive_bytes, candidate_archive_sha) != (EXPECTED_CANDIDATE["archive_bytes"], EXPECTED_CANDIDATE["archive_sha256"]):
        blockers.append("candidate archive identity cannot be recomputed")
    source_scope = inventory.get("source_scope", {})
    if source_scope.get("candidate_source_sha256") != EXPECTED_CANDIDATE_SOURCE_SHA:
        blockers.append("candidate source SHA map drift")
    else:
        for path, expected in EXPECTED_CANDIDATE_SOURCE_SHA.items():
            result = subprocess.run(["git", "-C", str(ROOT), "show", f"{EXPECTED_CANDIDATE['commit']}:{path}"], capture_output=True, check=False)
            if result.returncode != 0 or hashlib.sha256(result.stdout).hexdigest() != expected:
                blockers.append(f"candidate source SHA cannot be recomputed: {path}")
    if source_scope.get("upstream_source_blob_oid") != EXPECTED_UPSTREAM_BLOBS:
        blockers.append("upstream blob map drift")
    upstream_root = Path(os.environ.get("PYBERT_UPSTREAM", r"C:\Users\z3312\code\Py-bert-agent"))
    if not upstream_root.is_dir() or any(_git_blob(upstream_root, EXPECTED_UPSTREAM["commit"], path) != blob for path, blob in EXPECTED_UPSTREAM_BLOBS.items()):
        blockers.append("pinned upstream source blobs cannot be recomputed")
    audit = inventory.get("audit")
    if not isinstance(audit, dict) or audit.get("path") != AUDIT:
        blockers.append("audit path binding drift")
    expected_audit_keys = {"path", "sha256", "report_sha_binding", "source_map", "exact_file_bindings", "archive_harness"}
    if not isinstance(audit, dict) or set(audit) != expected_audit_keys:
        blockers.append("audit exact schema drift")
    if isinstance(audit, dict):
        if audit.get("report_sha_binding") != "exact_file_sha256" or audit.get("source_map") != "not_applicable_for_scoped_observation":
            blockers.append("audit exact values drift")
        if audit.get("archive_harness") != HARNESS:
            blockers.append("audit archive harness drift")
        expected_binding_keys = {"report_01", "report_02", "aggregate", "aggregator", "verifier", "mutation_tests"}
        if set(audit.get("exact_file_bindings", {})) != expected_binding_keys:
            blockers.append("audit exact file binding keys drift")
    if isinstance(audit, dict):
        audit_path = _safe(root, AUDIT)
        if not audit_path.is_file() or _sha(audit_path) != audit.get("sha256") or audit.get("sha256") != EXPECTED_AUDIT_SHA:
            blockers.append("audit SHA binding drift")
    binding = audit.get("exact_file_bindings", {}) if isinstance(audit, dict) else {}
    expected_report_hashes: list[dict[str, str]] = []
    for index, report_path in enumerate(REPORTS, start=1):
        report_file = _safe(root, report_path)
        report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.is_file() else {}
        report_sha = _sha(report_file) if report_file.is_file() else ""
        if report_sha != EXPECTED_REPORT_SHA[index - 1]:
            blockers.append(f"report_{index} content SHA drift")
        expected_report_hashes.append({"path": report_path, "sha256": report_sha})
        item = binding.get(f"report_{index:02d}") if isinstance(binding, dict) else None
        if item != {"path": report_path, "sha256": report_sha}:
            blockers.append(f"report_{index} file binding drift")
        if report.get("source_mode") != "git_archive_at_immutable_commit" or report.get("status") != "passed":
            blockers.append(f"report_{index} is not a passed archive report")
        run_id, nonce = EXPECTED_REPORT_RUNS[index - 1]
        if report.get("run_id") != run_id or report.get("fresh_run_nonce") != nonce:
            blockers.append(f"report_{index} run identity drift")
        if report.get("fixture") != {"path": "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml", "bytes": 1171, "sha256": "d63bb7ab3466ae70406cd2a555ae5a95cda1264021fed8fb1cdca85da961cc48", "archive_present": True}:
            blockers.append(f"report_{index} fixture drift")
        if _canonical_sha(report.get("upstream")) != "602a97a307d9c6e56495b7e96fc5e83af1fce78d458bee37fbdd13bbeedbcc38":
            blockers.append(f"report_{index} upstream identity drift")
        if _canonical_sha(report.get("toolchain")) != "989c809c7316841a720726bb71c2fbc0780b77f45b8bdfcbc6bd6bb272fe6b47":
            blockers.append(f"report_{index} toolchain drift")
        comparison = report.get("replay", {}).get("comparison")
        if _canonical_sha(comparison) != "45aef435fa7672961751974b65135d4803ee2cbe18501105d59f0d18df55f1fa" or comparison.get("status") != "passed" or len(comparison.get("arrays", [])) != 12 or not all(item.get("passed") is True for item in comparison.get("arrays", [])):
            blockers.append(f"report_{index} numeric comparison drift")
        # Reports also carry source inventories and lockfile hashes. The
        # immutable identity subset is the part this observation gate owns.
        candidate = report.get("candidate", {})
        if any(candidate.get(key) != EXPECTED_CANDIDATE[key] for key in ("commit", "tree", "archive_sha256")):
            blockers.append(f"report_{index} candidate identity drift")
        harness = report.get("harness")
        expected_harness = {
            "source_mode": "git_archive_at_immutable_commit",
            "runner": {"path": "tools/run_pb_01_legacy_leaf_replay.py", "sha256": HARNESS["tools/run_pb_01_legacy_leaf_replay.py"]},
            "custody_runner_helper": {"path": "tools/run_pb_02_direct_replay.py", "sha256": HARNESS["tools/run_pb_02_direct_replay.py"]},
        }
        if harness != expected_harness:
            blockers.append(f"report_{index} harness drift")
    aggregate_file = _safe(root, AGGREGATE)
    aggregate_sha = _sha(aggregate_file) if aggregate_file.is_file() else ""
    if aggregate_sha != EXPECTED_AGGREGATE_SHA or binding.get("aggregate") != {"path": AGGREGATE, "sha256": aggregate_sha}:
        blockers.append("aggregate file binding drift")
    aggregate = json.loads(aggregate_file.read_text(encoding="utf-8")) if aggregate_file.is_file() else {}
    expected_entries = [
        {"path": path, "sha256": item["sha256"], "run_id": None, "fresh_run_nonce": None}
        for path, item in zip(REPORTS, expected_report_hashes)
    ]
    for entry, report_path in zip(expected_entries, REPORTS):
        report = json.loads(_safe(root, report_path).read_text(encoding="utf-8"))
        entry["run_id"], entry["fresh_run_nonce"] = report.get("run_id"), report.get("fresh_run_nonce")
    if aggregate.get("status") != "passed" or aggregate.get("reports") != expected_entries:
        blockers.append("aggregate/report cross-binding drift")
    aggregator_binding = binding.get("aggregator")
    if aggregator_binding != {"path": AGGREGATOR, "sha256": EXPECTED_AGGREGATOR_SHA} or _sha(_safe(root, AGGREGATOR)) != EXPECTED_AGGREGATOR_SHA:
        blockers.append("aggregator binding drift")
    verifier_binding = binding.get("verifier")
    if not isinstance(verifier_binding, dict) or verifier_binding.get("path") != "tools/verify_pb_01_03_branch_inventory.py" or verifier_binding.get("sha256") != _sha(_safe(root, "tools/verify_pb_01_03_branch_inventory.py")):
        blockers.append("verifier binding drift")
    mutation_binding = binding.get("mutation_tests")
    if not isinstance(mutation_binding, dict) or mutation_binding.get("path") != "tools/test_verify_pb_01_03_branch_inventory.py" or mutation_binding.get("sha256") != _sha(_safe(root, "tools/test_verify_pb_01_03_branch_inventory.py")):
        blockers.append("mutation test binding drift")
    if inventory.get("claims", {}).get("global_pybert_parity") is not False:
        blockers.append("global parity claim must remain false")
    return {"status": "passed" if not blockers else "blocked", "blockers": blockers}


if __name__ == "__main__":
    result = verify_inventory()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "passed" else 1)
