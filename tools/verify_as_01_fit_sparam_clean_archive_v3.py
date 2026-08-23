"""Verify AS-01 clean-archive v3 bound evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/as-01-fit-sparam-bound-clean-archive-v3.yaml"
SOURCE = {
    "candidate": {"commit": "9914a23dc747d94405f2fed9227538ae7aea8629", "tree": "94a25c6254fdec3802b4946ec777ce65f22fdc0c", "archive_sha256": "4b6b7484974016ec58cc207676ed8ba4739e48fe62d256da8735bdefa43e5ccb"},
    "upstream": {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "archive_sha256": "282265e1c7b987407875a5c77fd1f2f0542cea9487407bb14b967a97b1ad6128"},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _has_absolute_path(value: object) -> bool:
    if isinstance(value, dict):
        return any(_has_absolute_path(key) or _has_absolute_path(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_absolute_path(item) for item in value)
    if not isinstance(value, str):
        return False
    return bool(re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/(?!sipi-(?:candidate|target)(?:/|$)))", value))


def verify(path: Path = MANIFEST, *, document: dict[str, object] | None = None) -> dict[str, object]:
    document = document if document is not None else yaml.safe_load(path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    if _has_absolute_path(document):
        blockers.append("absolute path disclosure")
    if document.get("schema") != "sipi.agent-spice-as-01-clean-archive-bound.v3" or document.get("status") != "completed_numeric_mismatch":
        blockers.append("manifest schema/status")
    scope = document.get("scope", {})
    if scope.get("parity_claim") is not False or scope.get("numeric_mismatch_open") is not True or scope.get("acceptance_tolerance") is not None:
        blockers.append("manifest parity flags")
    sources = document.get("source", {})
    if sources.get("materialization") != "git_archive_clean_temporary_root" or any(sources.get(role, {}).get(key) != value for role, expected in SOURCE.items() for key, value in expected.items()):
        blockers.append("source binding")
    for item in document.get("harness", {}).values():
        if not isinstance(item, dict):
            blockers.append("harness shape")
            continue
        bound = ROOT / item.get("path", "")
        if not item.get("path", "").startswith("tools/") or not bound.is_file() or item.get("sha256") != sha(bound):
            blockers.append("harness hash")
    report_hashes: list[str] = []
    binary_hashes: list[str] = []
    for item in document.get("reports", []):
        report_path = ROOT / item.get("path", "")
        if not item.get("path", "").startswith("docs/") or not report_path.is_file() or item.get("sha256") != sha(report_path):
            blockers.append("report hash")
            continue
        report_hashes.append(item["sha256"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if _has_absolute_path(report):
            blockers.append("absolute path disclosure")
        binary_hashes.append(report.get("build", {}).get("binary_sha256"))
        if report.get("status") != "completed_numeric_mismatch" or report.get("parity_claim") is not False or report.get("numeric_mismatch_open") is not True or report.get("comparison", {}).get("numeric_parity") is not False:
            blockers.append("report parity flags")
        if any(report.get(role, {}).get(key) != value for role, expected in SOURCE.items() for key, value in expected.items()):
            blockers.append("report source binding")
    aggregate = document.get("aggregate", {})
    aggregate_path = ROOT / aggregate.get("path", "")
    if not aggregate.get("path", "").startswith("docs/") or not aggregate_path.is_file() or aggregate.get("sha256") != sha(aggregate_path):
        blockers.append("aggregate hash")
    else:
        value = json.loads(aggregate_path.read_text(encoding="utf-8"))
        if value.get("status") != "completed_numeric_mismatch" or value.get("custody_valid") is not True or value.get("parity_claim") is not False or value.get("numeric_mismatch_open") is not True:
            blockers.append("aggregate contract")
        if [row.get("sha256") for row in value.get("reports", [])] != report_hashes:
            blockers.append("aggregate report binding")
        if value.get("candidate", {}).get("commit") != SOURCE["candidate"]["commit"] or value.get("candidate", {}).get("tree") != SOURCE["candidate"]["tree"]:
            blockers.append("aggregate source binding")
        if value.get("binary_sha256") != binary_hashes[0] or len(set(binary_hashes)) != 1:
            blockers.append("binary reproducibility binding")
    audit = document.get("audit", {})
    audit_path = ROOT / audit.get("path", "")
    if not audit.get("path", "").startswith("docs/") or not audit_path.is_file() or audit.get("sha256") != sha(audit_path):
        blockers.append("audit hash")
    return {"valid": not blockers, "blockers": blockers}


if __name__ == "__main__":
    result = verify(Path(sys.argv[1]) if len(sys.argv) > 1 else MANIFEST)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["valid"] else 1)
