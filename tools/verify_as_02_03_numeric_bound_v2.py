"""Verify bound AS-02/AS-03 numeric evidence without claiming parity."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = {
    "AS-02": ROOT / "docs/baselines/as-02-fit-sparam-cascade-numeric-bound-v2.yaml",
    "AS-03": ROOT / "docs/baselines/as-03-fit-yparam-numeric-bound-v2.yaml",
}
SOURCE = {"candidate": {"commit": "9914a23dc747d94405f2fed9227538ae7aea8629", "tree": "94a25c6254fdec3802b4946ec777ce65f22fdc0c", "archive_sha256": "02aefc5b1e23b22bc1716e9c2d7ada2905d57af68443cf9728c72bddb03eb0e4"}, "upstream": {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "archive_sha256": "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144"}}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _has_absolute_path(value: object) -> bool:
    """Reject host paths in evidence while allowing no path-bearing diagnostics."""
    if isinstance(value, dict):
        return any(_has_absolute_path(key) or _has_absolute_path(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_absolute_path(item) for item in value)
    if not isinstance(value, str):
        return False
    return bool(re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/(?!sipi-(?:candidate|target)(?:/|$)))", value))


def verify(path: Path, *, document: dict[str, object] | None = None) -> dict[str, object]:
    document = document if document is not None else yaml.safe_load(path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    if _has_absolute_path(document):
        blockers.append("absolute path disclosure")
    workflow = "AS-02" if "as-02" in path.name else "AS-03"
    if document.get("status") != "completed_numeric_mismatch_open" or document.get("parity_claim") is not False or document.get("numeric_parity") is not False:
        blockers.append("manifest parity flags")
    if any(document.get("source", {}).get(role, {}).get(key) != value for role, expected in SOURCE.items() for key, value in expected.items()):
        blockers.append("manifest source binding")
    for key in ("runner", "aggregator"):
        item = document.get("harness", {}).get(key, {})
        bound = ROOT / item.get("path", "")
        if not item.get("path", "").startswith("tools/") or not bound.is_file() or item.get("sha256") != sha(bound):
            blockers.append("harness hash")
    report_hashes = []
    binary_hashes = []
    for item in document.get("reports", []):
        report_path = ROOT / item.get("path", "")
        if not item.get("path", "").startswith("docs/") or not report_path.is_file() or item.get("sha256") != sha(report_path):
            blockers.append("report hash")
            continue
        report_hashes.append(item["sha256"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("workflow") != workflow or report.get("candidate") != SOURCE["candidate"] or report.get("upstream") != SOURCE["upstream"] or report.get("parity_claim") is not False or report.get("numeric_parity") is not False:
            blockers.append("report contract")
        binary_hashes.append(report.get("build", {}).get("binary_sha256"))
    aggregate = document.get("aggregate", {})
    aggregate_path = ROOT / aggregate.get("path", "")
    if not aggregate.get("path", "").startswith("docs/") or not aggregate_path.is_file() or aggregate.get("sha256") != sha(aggregate_path):
        blockers.append("aggregate hash")
    else:
        value = json.loads(aggregate_path.read_text(encoding="utf-8"))
        if value.get("status") != "completed_numeric_mismatch_open" or value.get("custody_valid") is not True or value.get("workflow") != workflow:
            blockers.append("aggregate contract")
        if [item.get("sha256") for item in value.get("reports", [])] != report_hashes or len(set(binary_hashes)) != 1:
            blockers.append("aggregate report binding")
    audit = document.get("audit", {})
    audit_path = ROOT / audit.get("path", "")
    if not audit.get("path", "").startswith("docs/") or not audit_path.is_file() or audit.get("sha256") != sha(audit_path):
        blockers.append("audit hash")
    return {"valid": not blockers, "blockers": blockers}


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else MANIFESTS["AS-02"]
    result = verify(path)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["valid"] else 1)
