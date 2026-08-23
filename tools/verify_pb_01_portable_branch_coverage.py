"""Verify the content-addressed PB-01 portable branch inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/baselines/pb-01-portable-branch-coverage.v1.yaml"


def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    if document.get("schema") != "sipi.pb-01-portable-branch-coverage.v1":
        errors.append("schema mismatch")
    if document.get("portable_missing") != []:
        errors.append("portable_missing must be an empty list")
    rows = document.get("rows")
    if not isinstance(rows, dict) or set(rows) != {"PB-01"}:
        errors.append("rows must contain exactly PB-01")
        rows = rows if isinstance(rows, dict) else {}
    entry = rows.get("PB-01", {})
    branches = entry.get("branches", []) if isinstance(entry, dict) else []
    if not branches:
        errors.append("PB-01 has no branch entries")
    seen: set[str] = set()
    for branch in branches:
        if not isinstance(branch, dict):
            errors.append("PB-01 branch is not a mapping")
            continue
        branch_id = branch.get("id")
        if not isinstance(branch_id, str) or not branch_id:
            errors.append("PB-01 branch has no id")
        elif branch_id in seen:
            errors.append(f"PB-01 duplicate branch {branch_id}")
        else:
            seen.add(branch_id)
        if branch.get("status") == "missing":
            errors.append(f"PB-01/{branch_id} is marked missing")
        if branch.get("status") in {"external_blocked", "implemented_blocked"} and not branch.get("blocker"):
            errors.append(f"PB-01/{branch_id} blocker is missing")
        if not isinstance(branch.get("test"), str) or not branch["test"]:
            errors.append(f"PB-01/{branch_id} test evidence is missing")
    source = document.get("source", {})
    source_files = source.get("source_files", {}) if isinstance(source, dict) else {}
    if not isinstance(source_files, dict) or not source_files:
        errors.append("content-addressed source_files are missing")
    else:
        for relative, expected in source_files.items():
            path = root / relative
            if not path.is_file():
                errors.append(f"source file is missing: {relative}")
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                errors.append(f"source hash mismatch: {relative}")
    blockers = document.get("external_blockers")
    if not isinstance(blockers, list) or not blockers:
        errors.append("external_blockers must remain explicit")
    claims = document.get("claims", {})
    if not isinstance(claims, dict) or claims.get("global_row_closed") is not False:
        errors.append("global closure claim must remain false")
    return {
        "valid": not errors,
        "errors": errors,
        "portable_missing": document.get("portable_missing"),
        "external_blockers": blockers,
        "source_file_count": len(source_files) if isinstance(source_files, dict) else 0,
    }


def main() -> int:
    document = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    result = verify(document)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
