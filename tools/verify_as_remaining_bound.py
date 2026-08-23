"""Verify immutable AS-02..AS-06 v2 reports and manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_COMMIT = "64b783f66d7e986d0975be5ac3946b453b15c4ed"
CANDIDATE_TREE = "0e11721f2bb5b564002820cc7a5aaab45e30ba3b"
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
UPSTREAM_ROOT = Path(r"C:\Users\z3312\code\agent-spice")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ROWS = {"AS-02", "AS-03", "AS-04", "AS-05", "AS-06"}
MANIFESTS = {
    "AS-02": ROOT / "docs/baselines/as-02-fit-sparam-cascade-direct-port.v2.yaml",
    "AS-03": ROOT / "docs/baselines/as-03-fit-yparam-direct-port.v2.yaml",
    "AS-04": ROOT / "docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml",
    "AS-05": ROOT / "docs/baselines/as-05-run-hspice-rust-control-direct-port.v2.yaml",
    "AS-06": ROOT / "docs/baselines/as-06-run-rfm-direct-port.v2.yaml",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def no_absolute(value: Any) -> bool:
    if isinstance(value, dict):
        return all(no_absolute(item) for item in value.values())
    if isinstance(value, list):
        return all(no_absolute(item) for item in value)
    if not isinstance(value, str):
        return True
    normalized = value.replace("\\", "/")
    return not bool(re.match(r"^[A-Za-z]:/|^/(?:Users|home)/|^//", normalized))


def repo_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value.replace("\\", "/")
    return no_absolute(normalized) and not normalized.startswith("/") and ".." not in normalized.split("/")


def git_archive_sha(repo: Path, revision: str) -> str:
    payload = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", revision], check=True, stdout=subprocess.PIPE).stdout
    return hashlib.sha256(payload).hexdigest()


def verify(document: dict[str, Any], path: Path = ROOT / "docs/baselines/as-02-bound.v2.yaml") -> dict[str, Any]:
    blockers: list[str] = []
    schema = str(document.get("schema", ""))
    match = re.fullmatch(r"sipi\.(as-0[2-6])-[a-z0-9-]+-direct-port\.v2", schema)
    row = match.group(1).upper() if match else ""
    if not row:
        blockers.append("schema")
    source = document.get("source") or {}
    candidate = source.get("candidate") if isinstance(source, dict) else {}
    upstream = source.get("upstream") if isinstance(source, dict) else {}
    if candidate.get("commit") != CANDIDATE_COMMIT or candidate.get("tree") != CANDIDATE_TREE:
        blockers.append("candidate identity")
    if upstream.get("commit") != UPSTREAM_COMMIT or upstream.get("tree") != UPSTREAM_TREE:
        blockers.append("upstream identity")
    if source.get("materialization") != {"candidate": "git_archive_clean_temporary_root", "overlay_current_worktree": False}:
        blockers.append("materialization")
    if path.exists():
        try:
            if candidate.get("archive_sha256") != git_archive_sha(ROOT, CANDIDATE_COMMIT):
                blockers.append("candidate archive")
            if upstream.get("archive_sha256") != git_archive_sha(UPSTREAM_ROOT, UPSTREAM_COMMIT):
                blockers.append("upstream archive")
        except (OSError, subprocess.CalledProcessError):
            blockers.append("archive materialization unavailable")
    harness = document.get("harness") or {}
    for key in ("runner", "helper", "aggregator", "verifier", "mutation_tests"):
        record = harness.get(key) if isinstance(harness, dict) else None
        if not isinstance(record, dict) or not repo_relative(record.get("path")):
            blockers.append(f"harness {key}")
        else:
            target = ROOT / record["path"]
            expected_hash = sha(target) if key != "helper" else hashlib.sha256(subprocess.run(["git", "-C", str(ROOT), "show", f"{CANDIDATE_COMMIT}:{record['path']}"], check=True, stdout=subprocess.PIPE).stdout).hexdigest()
            if not target.is_file() or record.get("sha256") != expected_hash:
                blockers.append(f"harness hash {key}")
    reports = document.get("reports")
    if not isinstance(reports, list) or len(reports) != 2:
        blockers.append("reports")
        reports = []
    report_docs: list[dict[str, Any]] = []
    for item in reports:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            blockers.append("report record")
            continue
        if not repo_relative(item.get("path")):
            blockers.append("report path escape")
            continue
        report_path = ROOT / item["path"]
        if not report_path.is_file() or item.get("sha256") != sha(report_path):
            blockers.append("report hash")
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report_docs.append(report)
        if report.get("source_mode") != "candidate_and_upstream_git_archive_at_immutable_commit" or report.get("parity_claim") is not False or report.get("numeric_parity") is not False or report.get("replay", {}).get("corpus_expected") is not True:
            blockers.append("report overclaim")
        if report.get("candidate") != candidate or any(report.get("upstream", {}).get(key) != upstream.get(key) for key in ("commit", "tree", "archive_sha256")):
            blockers.append("report source binding")
        if report.get("runner", {}).get("path") != harness.get("runner", {}).get("path") or report.get("runner", {}).get("sha256") != harness.get("runner", {}).get("sha256"):
            blockers.append("report runner binding")
        if report.get("helper", {}).get("path") != harness.get("helper", {}).get("path") or report.get("helper", {}).get("sha256") != harness.get("helper", {}).get("sha256"):
            blockers.append("report helper binding")
        if not repo_relative(report.get("runner", {}).get("path")) or not repo_relative(report.get("helper", {}).get("path")):
            blockers.append("report harness path escape")
        if not no_absolute(report):
            blockers.append("report absolute path")
        if not isinstance(report.get("fresh_run_nonce"), str) or HEX64.fullmatch(report["fresh_run_nonce"]) is None:
            blockers.append("report nonce")
    if len(report_docs) == 2:
        if report_docs[0].get("run_id") == report_docs[1].get("run_id") or report_docs[0].get("fresh_run_nonce") == report_docs[1].get("fresh_run_nonce"):
            blockers.append("independent run identity")
        if report_docs[0].get("toolchain") != report_docs[1].get("toolchain"):
            blockers.append("toolchain drift")
        if any(document.get("toolchain") != report.get("toolchain") for report in report_docs):
            blockers.append("manifest toolchain binding")
        for key in ("candidate", "upstream", "runner", "helper", "toolchain"):
            if report_docs[0].get(key) != report_docs[1].get(key):
                blockers.append(f"cross-run drift:{key}")
        fixture = document.get("fixture") or {}
        expected_fixture = hashlib.sha256(canonical(report_docs[0].get("corpus"))).hexdigest()
        if fixture.get("corpus_sha256") != expected_fixture or fixture.get("input_tree_sha256") != [report.get("replay", {}).get("input_tree_sha256") for report in report_docs]:
            blockers.append("fixture/input binding")
    aggregate = document.get("aggregate") or {}
    if not repo_relative(aggregate.get("path")):
        blockers.append("aggregate path escape")
    aggregate_path = ROOT / str(aggregate.get("path", "__missing__"))
    if not aggregate_path.is_file() or aggregate.get("sha256") != sha(aggregate_path):
        blockers.append("aggregate hash")
    else:
        agg = json.loads(aggregate_path.read_text(encoding="utf-8"))
        if agg.get("custody_valid") is not True or agg.get("parity_claim") is not False or not no_absolute(agg):
            blockers.append("aggregate contract")
        if agg.get("candidate") != candidate or any(agg.get("upstream", {}).get(key) != upstream.get(key) for key in ("commit", "tree", "archive_sha256")) or agg.get("runner") != harness.get("runner") or agg.get("helper") != harness.get("helper") or agg.get("toolchain") != document.get("toolchain"):
            blockers.append("aggregate complete binding")
        if any(not repo_relative(item.get("path")) for item in agg.get("reports", []) if isinstance(item, dict)):
            blockers.append("aggregate report path escape")
        if len(report_docs) == 2 and [row.get("sha256") for row in reports] != [item.get("sha256") for item in agg.get("reports", [])]:
            blockers.append("aggregate report binding")
    audit = document.get("audit") or {}
    if not repo_relative(audit.get("path")):
        blockers.append("audit path escape")
    audit_path = ROOT / str(audit.get("path", "__missing__"))
    if not audit_path.is_file() or audit.get("sha256") != sha(audit_path):
        blockers.append("audit hash")
    if document.get("status") not in {"completed_portable_observation_open", "completed_external_blocker_open"}:
        blockers.append("status")
    return {"valid": not blockers, "row": row, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    result = verify(yaml.safe_load(path.read_text(encoding="utf-8")), path)
    print("valid" if result["valid"] else "blocked")
    for blocker in result["blockers"]:
        print(f"- {blocker}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
