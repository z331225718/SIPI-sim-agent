"""Strict custody verifier for AS-02/AS-03 v3 numeric evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = {
    "AS-02": ROOT / "docs/baselines/as-02-fit-sparam-cascade-numeric-bound-v3.yaml",
    "AS-03": ROOT / "docs/baselines/as-03-fit-yparam-numeric-scope-v1.yaml",
}
UPSTREAM_SOURCE = {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "archive_sha256": "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144"}
CANDIDATE_SOURCE = {"commit": "aeb09982f360e73159d1335c6e0dd77d1176e65a", "tree": "4d0411d9439bed2ff5410b56f799ac47583bf43a", "archive_sha256": "272beba9cff45b449cf84c19dfcd026f5d42a3d470cdd18bf38a731b3780f4e0"}
RUNNER_PATH = "tools/run_as_02_03_numeric_bound_v3.py"
AGGREGATOR_PATH = "tools/aggregate_as_02_03_numeric_bound_v3.py"
HARNESS_SHA = {RUNNER_PATH: "1acc6d619b37f0ea1139ce4a21117024b723a5bf934b42b927fa6af3670e9c61", AGGREGATOR_PATH: "d951474d93d2c0cb110ab15ad2a961905d4c067db5b9cff6ddf91b3f96fbbae4"}
FIXTURE_SHA = "4da06c257a0f0108e4391d65f894b6bb0d62a24a8f00f82f0f0734e061f5de70"
AUDIT_PATH = "docs/baselines/audits/2026-08-24-as-02-03-numeric-bound-v3.md"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TOOL_KEYS = {"cargo", "rustc", "python"}
TOOL_ITEM_KEYS = {"schema", "role", "executable", "path_redacted", "file_sha256", "version_sha256", "exit_code"}
AS02_METRIC_KEYS = {"candidate_block_rms", "candidate_cascade_mean_rms", "candidate_snapshot", "upstream_block_rms", "upstream_cascade_mean_rms", "upstream_snapshot"}
AS03_METRIC_KEYS = {"candidate_snapshot", "candidate_y_mean_rms_siemens", "candidate_y_rms_siemens", "upstream_snapshot", "upstream_y_mean_rms_siemens", "upstream_y_rms_siemens"}
SCHEMA = "sipi.agent-spice-as-numeric-bound.v3"
AGGREGATE_SCHEMA = "sipi.agent-spice-as-numeric-bound-aggregate.v3"
WRAPPER_POLICY = {"schema": "sipi.path-free-wrapper-policy.v1", "clear_inherited_rustc_wrapper": True, "clear_inherited_rustc_workspace_wrapper": True, "rustc_wrapper": "unset", "rustc_workspace_wrapper": "unset"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commit_blob_sha(commit: str, path: str) -> str | None:
    try:
        data = subprocess.check_output(["git", "-C", str(ROOT), "cat-file", "blob", f"{commit}:{path}"])
    except (OSError, subprocess.CalledProcessError):
        return None
    return hashlib.sha256(data).hexdigest()


def valid_toolchain(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != TOOL_KEYS:
        return False
    for role, item in value.items():
        if not isinstance(item, dict) or set(item) != TOOL_ITEM_KEYS or item.get("schema") != "sipi.path-free-tool-identity.v1":
            return False
        executable = item.get("executable")
        if not isinstance(executable, str) or not executable or Path(executable).name != executable:
            return False
        if item.get("role") != role or item.get("path_redacted") is not True or item.get("exit_code") != 0:
            return False
        if not HEX64.fullmatch(item.get("file_sha256", "")) or not HEX64.fullmatch(item.get("version_sha256", "")) or set(item["file_sha256"]) == {"0"} or set(item["version_sha256"]) == {"0"}:
            return False
    return True


def finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def valid_metrics(workflow: str, metrics: object) -> bool:
    if not isinstance(metrics, dict):
        return False
    if set(metrics) != (AS02_METRIC_KEYS if workflow == "AS-02" else AS03_METRIC_KEYS):
        return False
    def nested_finite(value: object) -> bool:
        if isinstance(value, dict):
            return all(nested_finite(item) for item in value.values())
        if isinstance(value, list):
            return all(nested_finite(item) for item in value)
        if value is None or isinstance(value, (str, bool)):
            return True
        return finite(value)
    if not nested_finite(metrics):
        return False
    if workflow == "AS-02":
        required = ("upstream_cascade_mean_rms", "candidate_cascade_mean_rms", "upstream_block_rms", "candidate_block_rms")
        if any(not finite(metrics.get(key)) for key in required[:2]):
            return False
        if not all(isinstance(metrics.get(key), list) and metrics[key] and all(finite(x) for x in metrics[key]) for key in required[2:]):
            return False
        return len(metrics["upstream_block_rms"]) == len(metrics["candidate_block_rms"]) and abs(metrics["upstream_cascade_mean_rms"] - metrics["candidate_cascade_mean_rms"]) > 0.0
    required = ("upstream_y_rms_siemens", "candidate_y_rms_siemens", "upstream_y_mean_rms_siemens", "candidate_y_mean_rms_siemens")
    return all(finite(metrics.get(key)) for key in required) and max(abs(metrics["upstream_y_rms_siemens"] - metrics["candidate_y_rms_siemens"]), abs(metrics["upstream_y_mean_rms_siemens"] - metrics["candidate_y_mean_rms_siemens"])) <= 1.0e-12


def repo_file(value: object, prefix: str) -> Path | None:
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    path = ROOT / candidate
    return path if path.is_file() else None


def has_absolute(value: object) -> bool:
    if isinstance(value, dict):
        return any(has_absolute(k) or has_absolute(v) for k, v in value.items())
    if isinstance(value, list):
        return any(has_absolute(v) for v in value)
    return isinstance(value, str) and bool(re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/(?!sipi-(?:candidate|target)(?:/|$)))", value))


def verify(path: Path, document: dict[str, object] | None = None) -> dict[str, object]:
    doc = document if document is not None else yaml.safe_load(path.read_text(encoding="utf-8"))
    workflow = "AS-02" if "as-02" in path.name else "AS-03"
    blockers: list[str] = []
    if has_absolute(doc):
        blockers.append("absolute path disclosure")
    if doc.get("schema") != ("sipi.as-03-fit-yparam-numeric-scope-v1" if workflow == "AS-03" else "sipi.as-02-fit-sparam-cascade-numeric-bound-v3"):
        blockers.append("manifest schema")
    if workflow == "AS-03":
        if doc.get("status") != "scoped_numeric_parity_observation" or doc.get("parity_claim") is not False or doc.get("scoped_observation_passed") is not True or doc.get("global_row_closed") is not False:
            blockers.append("scoped status")
        if doc.get("scope", {}).get("tolerance") != 1.0e-12:
            blockers.append("scope tolerance")
    else:
        if doc.get("status") != "completed_numeric_mismatch_open" or doc.get("parity_claim") is not False or doc.get("numeric_parity") is not False or doc.get("acceptance_tolerance") is not False:
            blockers.append("open mismatch status")
    if doc.get("fixture_sha256") != FIXTURE_SHA:
        blockers.append("manifest fixture identity")
    source = doc.get("source", {})
    candidate_source = source.get("candidate", {})
    if source.get("upstream") != UPSTREAM_SOURCE or candidate_source != CANDIDATE_SOURCE:
        blockers.append("source binding")
    for key, expected_path in (("runner", RUNNER_PATH), ("aggregator", AGGREGATOR_PATH)):
        item = doc.get("harness", {}).get(key, {})
        file = repo_file(item.get("path"), "tools/")
        commit_sha = commit_blob_sha(CANDIDATE_SOURCE["commit"], expected_path)
        if item.get("path") != expected_path or file is None or item.get("sha256") != HARNESS_SHA[expected_path] or sha(file) != HARNESS_SHA[expected_path] or commit_sha != HARNESS_SHA[expected_path]:
            blockers.append(f"{key} binding")
    report_items = doc.get("reports", [])
    reports: list[dict[str, object]] = []
    report_hashes: list[str] = []
    report_ids: list[str] = []
    report_nonces: list[str] = []
    for item in report_items:
        report_file = repo_file(item.get("path"), "docs/") if isinstance(item, dict) else None
        if report_file is None or item.get("sha256") != sha(report_file):
            blockers.append("report path/hash")
            continue
        value = json.loads(report_file.read_text(encoding="utf-8"))
        reports.append(value); report_hashes.append(item["sha256"]); report_ids.append(value.get("run_id")); report_nonces.append(value.get("fresh_run_nonce"))
        if has_absolute(value) or value.get("schema") != SCHEMA or value.get("workflow") != workflow or value.get("status") != "completed_numeric_mismatch_open" or value.get("parity_claim") is not False or value.get("numeric_parity") is not False:
            blockers.append("report schema/status")
        if value.get("candidate") != candidate_source or value.get("upstream") != UPSTREAM_SOURCE:
            blockers.append("report source binding")
        if value.get("runner", {}).get("repo_relative_path") != RUNNER_PATH or value.get("runner", {}).get("sha256") != HARNESS_SHA[RUNNER_PATH]:
            blockers.append("report runner binding")
        if value.get("wrapper_policy") != WRAPPER_POLICY:
            blockers.append("wrapper policy")
        fixture = value.get("fixture", {})
        if fixture.get("kind") != "fixed_touchstone_line_s2p_v1" or fixture.get("generated_by_runner_constant") != "tools/run_as_02_03_numeric_bound_v3.py:FIXTURE" or fixture.get("sha256") != FIXTURE_SHA or fixture.get("sha256") != value.get("fixture_sha256"):
            blockers.append("fixture identity")
        if not valid_toolchain(value.get("toolchain")):
            blockers.append("toolchain schema")
        if not isinstance(value.get("run_id"), str) or not value["run_id"] or not HEX64.fullmatch(value.get("fresh_run_nonce", "")):
            blockers.append("run identity")
        if not valid_metrics(workflow, value.get("metrics")):
            blockers.append("finite metric contract")
        if not isinstance(value.get("build", {}).get("binary_sha256"), str) or set(value.get("execution", {})) != {"upstream", "candidate", "upstream_report_sha256", "candidate_report_sha256"}:
            blockers.append("build/execution contract")
    if len(reports) != 2 or len(set(report_hashes)) != 2 or len(set(report_ids)) != 2 or len(set(report_nonces)) != 2:
        blockers.append("two-run identity")
    if len(reports) == 2:
        for key in ("candidate", "upstream", "toolchain", "fixture", "fixture_sha256", "runner", "wrapper_policy", "metrics"):
            if reports[0].get(key) != reports[1].get(key):
                blockers.append(f"cross-run drift:{key}")
    aggregate = doc.get("aggregate", {})
    aggregate_file = repo_file(aggregate.get("path"), "docs/") if isinstance(aggregate, dict) else None
    if aggregate_file is None or aggregate.get("sha256") != sha(aggregate_file):
        blockers.append("aggregate path/hash")
    else:
        value = json.loads(aggregate_file.read_text(encoding="utf-8"))
        expected_ids = [{"path": item["path"], "sha256": item["sha256"], "run_id": report.get("run_id"), "fresh_run_nonce": report.get("fresh_run_nonce")} for item, report in zip(report_items, reports)]
        aggregate_binding = sha(ROOT / AGGREGATOR_PATH) == HARNESS_SHA[AGGREGATOR_PATH] and commit_blob_sha(CANDIDATE_SOURCE["commit"], AGGREGATOR_PATH) == HARNESS_SHA[AGGREGATOR_PATH]
        if has_absolute(value) or value.get("schema") != AGGREGATE_SCHEMA or value.get("workflow") != workflow or value.get("status") != "completed_numeric_mismatch_open" or value.get("custody_valid") is not True or value.get("reports") != expected_ids or value.get("candidate") != candidate_source or value.get("upstream") != UPSTREAM_SOURCE or value.get("runner") != reports[0].get("runner") or value.get("toolchain") != reports[0].get("toolchain") or value.get("fixture") != reports[0].get("fixture") or value.get("metrics") != reports[0].get("metrics") or not aggregate_binding or not valid_metrics(workflow, value.get("metrics")):
            blockers.append("aggregate binding")
    audit = doc.get("audit", {})
    audit_file = repo_file(audit.get("path"), "docs/") if isinstance(audit, dict) else None
    aggregate_path_value = aggregate.get("path") if isinstance(aggregate, dict) else ""
    aggregate_sha_value = aggregate.get("sha256") if isinstance(aggregate, dict) else ""
    audit_binding = f"Aggregate path: `{aggregate_path_value}`; SHA256: `{aggregate_sha_value}`" in audit_file.read_text(encoding="utf-8") if audit_file is not None else False
    if audit.get("path") != AUDIT_PATH or audit_file is None or audit.get("sha256") != sha(audit_file) or not audit_binding:
        blockers.append("audit path/hash")
    return {"valid": not blockers, "blockers": blockers}


if __name__ == "__main__":
    selected = Path(sys.argv[1]) if len(sys.argv) > 1 else MANIFESTS["AS-02"]
    result = verify(selected)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["valid"] else 1)
