"""Verify the content-addressed PB-02..PB-05 branch inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/baselines/pb-02-05-branch-coverage-matrix.v1.yaml"
ROWS = ("PB-02", "PB-03", "PB-04", "PB-05")
ALLOWED_EXTERNAL_STATUSES = {
    "external_blocked",
    "pb01_dependency",
    "implemented_blocked",
    "shadow_only",
}


def verify(document: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    if document.get("schema") != "pybert.pb-02-05-branch-coverage.v1":
        errors.append("schema mismatch")
    if document.get("portable_missing") != []:
        errors.append("portable_missing must be an empty list")
    rows = document.get("rows")
    if not isinstance(rows, dict) or set(rows) != set(ROWS):
        errors.append("rows must contain exactly PB-02, PB-03, PB-04, PB-05")
        rows = rows if isinstance(rows, dict) else {}
    for row in ROWS:
        entry = rows.get(row, {})
        branches = entry.get("branches", []) if isinstance(entry, dict) else []
        if not branches:
            errors.append(f"{row} has no branch entries")
            continue
        seen: set[str] = set()
        for branch in branches:
            if not isinstance(branch, dict):
                errors.append(f"{row} branch is not a mapping")
                continue
            branch_id = branch.get("id")
            if not isinstance(branch_id, str) or not branch_id:
                errors.append(f"{row} branch has no id")
            elif branch_id in seen:
                errors.append(f"{row} duplicate branch {branch_id}")
            else:
                seen.add(branch_id)
            status = branch.get("status")
            if status == "missing":
                errors.append(f"{row}/{branch_id} is marked missing")
            if status in ALLOWED_EXTERNAL_STATUSES and not branch.get("blocker"):
                errors.append(f"{row}/{branch_id} blocker is missing")
            if not isinstance(branch.get("test"), str) or not branch["test"]:
                errors.append(f"{row}/{branch_id} test evidence is missing")

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

    blockers = document.get("external_blockers", [])
    if not isinstance(blockers, list) or not blockers:
        errors.append("external_blockers must remain explicit")
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
