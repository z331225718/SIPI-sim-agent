"""Strict custody verifier for AS-02/AS-03 v3 numeric evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = {
    "AS-02": ROOT / "docs/baselines/as-02-fit-sparam-cascade-numeric-bound-v3.yaml",
    "AS-03": ROOT / "docs/baselines/as-03-fit-yparam-numeric-scope-v1.yaml",
}
SOURCE = {
    "candidate": {"commit": "706191a1d0a9be7fed77e10b7ba90195d01b1911", "tree": "ef51159ea5d471405d3018e8eadc10df607b6e2f", "archive_sha256": "a7535bd0f641f6f22e72ad9da16f97fc034c95b3666ace9a0f20859bb6b7f179"},
    "upstream": {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "archive_sha256": "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144"},
}
RUNNER_PATH = "tools/run_as_02_03_numeric_bound_v3.py"
AGGREGATOR_PATH = "tools/aggregate_as_02_03_numeric_bound_v3.py"
SCHEMA = "sipi.agent-spice-as-numeric-bound.v3"
AGGREGATE_SCHEMA = "sipi.agent-spice-as-numeric-bound-aggregate.v3"
WRAPPER_POLICY = {"schema": "sipi.path-free-wrapper-policy.v1", "clear_inherited_rustc_wrapper": True, "clear_inherited_rustc_workspace_wrapper": True, "rustc_wrapper": "unset", "rustc_workspace_wrapper": "unset"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        if doc.get("status") != "scoped_numeric_parity_observation" or doc.get("parity_claim") is not True or doc.get("global_row_closed") is not False:
            blockers.append("scoped status")
        if doc.get("scope", {}).get("tolerance") != 1.0e-12:
            blockers.append("scope tolerance")
    else:
        if doc.get("status") != "completed_numeric_mismatch_open" or doc.get("parity_claim") is not False or doc.get("numeric_parity") is not False or doc.get("acceptance_tolerance") is not False:
            blockers.append("open mismatch status")
    if doc.get("source") != SOURCE:
        blockers.append("source binding")
    for key, expected_path in (("runner", RUNNER_PATH), ("aggregator", AGGREGATOR_PATH)):
        item = doc.get("harness", {}).get(key, {})
        file = repo_file(item.get("path"), "tools/")
        if item.get("path") != expected_path or file is None or item.get("sha256") != sha(file):
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
        if value.get("schema") != SCHEMA or value.get("workflow") != workflow or value.get("status") != "completed_numeric_mismatch_open" or value.get("parity_claim") is not False or value.get("numeric_parity") is not False:
            blockers.append("report schema/status")
        if value.get("candidate") != SOURCE["candidate"] or value.get("upstream") != SOURCE["upstream"]:
            blockers.append("report source binding")
        if value.get("runner", {}).get("repo_relative_path") != RUNNER_PATH or value.get("runner", {}).get("sha256") != sha(ROOT / RUNNER_PATH):
            blockers.append("report runner binding")
        if value.get("wrapper_policy") != WRAPPER_POLICY:
            blockers.append("wrapper policy")
        fixture = value.get("fixture", {})
        if fixture.get("kind") != "fixed_touchstone_line_s2p_v1" or fixture.get("generated_by_runner_constant") != "tools/run_as_02_03_numeric_bound_v3.py:FIXTURE" or fixture.get("sha256") != value.get("fixture_sha256"):
            blockers.append("fixture identity")
        if any(tool.get("schema") != "sipi.path-free-tool-identity.v1" or tool.get("path_redacted") is not True for tool in value.get("toolchain", {}).values()):
            blockers.append("toolchain schema")
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
        if value.get("schema") != AGGREGATE_SCHEMA or value.get("workflow") != workflow or value.get("status") != "completed_numeric_mismatch_open" or value.get("custody_valid") is not True or value.get("reports") != expected_ids or value.get("candidate") != SOURCE["candidate"] or value.get("upstream") != SOURCE["upstream"] or value.get("runner") != reports[0].get("runner") or value.get("metrics") != reports[0].get("metrics"):
            blockers.append("aggregate binding")
    audit = doc.get("audit", {})
    audit_file = repo_file(audit.get("path"), "docs/") if isinstance(audit, dict) else None
    if audit_file is None or audit.get("sha256") != sha(audit_file):
        blockers.append("audit path/hash")
    return {"valid": not blockers, "blockers": blockers}


if __name__ == "__main__":
    selected = Path(sys.argv[1]) if len(sys.argv) > 1 else MANIFESTS["AS-02"]
    result = verify(selected)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["valid"] else 1)
