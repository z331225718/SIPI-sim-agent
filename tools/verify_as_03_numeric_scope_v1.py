"""Verify the narrow AS-03 fixture-scoped numeric parity observation."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/as-03-fit-yparam-numeric-scope-v1.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _has_absolute(value: object) -> bool:
    if isinstance(value, dict):
        return any(_has_absolute(k) or _has_absolute(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_absolute(v) for v in value)
    return isinstance(value, str) and bool(re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/(?!sipi-(?:candidate|target)(?:/|$)))", value))


def _repo_file(value: object, prefix: str) -> Path | None:
    if not isinstance(value, str) or not value.startswith(prefix) or ".." in Path(value).parts:
        return None
    path = ROOT / value
    return path if path.is_file() else None


def verify(path: Path = MANIFEST, document: dict[str, object] | None = None) -> dict[str, object]:
    doc = document if document is not None else yaml.safe_load(path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    if _has_absolute(doc) or doc.get("global_row_closed") is not False:
        blockers.append("scope or path contract")
    source = doc.get("source", {})
    expected = {"commit": "706191a1d0a9be7fed77e10b7ba90195d01b1911", "tree": "ef51159ea5d471405d3018e8eadc10df607b6e2f"}
    if source.get("candidate", {}).get("commit") != expected["commit"] or source.get("candidate", {}).get("tree") != expected["tree"]:
        blockers.append("candidate binding")
    report_hashes: list[str] = []
    reports = doc.get("reports", [])
    for item in reports:
        report_path = _repo_file(item.get("path"), "docs/") if isinstance(item, dict) else None
        if report_path is None or item.get("sha256") != sha(report_path):
            blockers.append("report path/hash")
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report_hashes.append(item["sha256"])
        if report.get("workflow") != "AS-03" or report.get("candidate", {}).get("commit") != expected["commit"] or report.get("parity_claim") is not False or report.get("numeric_parity") is not False:
            blockers.append("report contract")
        metrics = report.get("metrics", {})
        if abs(metrics.get("candidate_y_rms_siemens", 1.0) - metrics.get("upstream_y_rms_siemens", 0.0)) > 1e-12 or abs(metrics.get("candidate_y_mean_rms_siemens", 1.0) - metrics.get("upstream_y_mean_rms_siemens", 0.0)) > 1e-12:
            blockers.append("scoped numeric mismatch")
    aggregate = doc.get("aggregate", {})
    aggregate_path = _repo_file(aggregate.get("path"), "docs/") if isinstance(aggregate, dict) else None
    if aggregate_path is None or aggregate.get("sha256") != sha(aggregate_path):
        blockers.append("aggregate path/hash")
    else:
        value = json.loads(aggregate_path.read_text(encoding="utf-8"))
        if value.get("workflow") != "AS-03" or value.get("status") != "completed_numeric_mismatch_open" or value.get("custody_valid") is not True or [x.get("sha256") for x in value.get("reports", [])] != report_hashes:
            blockers.append("aggregate contract")
    for key in ("runner", "aggregator"):
        item = doc.get("harness", {}).get(key, {})
        tool_path = _repo_file(item.get("path"), "tools/") if isinstance(item, dict) else None
        if tool_path is None or item.get("sha256") != sha(tool_path):
            blockers.append("harness hash")
    audit = doc.get("audit", {})
    audit_path = _repo_file(audit.get("path"), "docs/") if isinstance(audit, dict) else None
    if audit_path is None or audit.get("sha256") != sha(audit_path):
        blockers.append("audit hash")
    return {"valid": not blockers, "blockers": blockers}


if __name__ == "__main__":
    result = verify(Path(sys.argv[1]) if len(sys.argv) > 1 else MANIFEST)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["valid"] else 1)
