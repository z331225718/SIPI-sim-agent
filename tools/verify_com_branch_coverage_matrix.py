"""Verify the COM-02/COM-04 portable branch coverage matrix."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "baselines" / "audits" / "2026-08-23-com-02-04-branch-coverage-matrix.v1.yaml"
ALLOWED_EXTERNAL = {"plotting_format", "matlab_engine", "proprietary_golden"}
SOURCE_UNIMPLEMENTED = {"wiener_hopf"}


class VerificationError(RuntimeError):
    pass


def verify(path: Path = DEFAULT_MATRIX) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError(str(error)) from error
    if not isinstance(document, dict) or document.get("schema") != "sipi.com-02-04.branch-coverage.v1":
        raise VerificationError("matrix schema drift")
    if document.get("portable_missing") != []:
        raise VerificationError("portable scope is not closed")
    blocked = document.get("external_blocked")
    if not isinstance(blocked, list) or {item.get("branch") for item in blocked} != ALLOWED_EXTERNAL:
        raise VerificationError("external blocker drift")
    source_unimplemented = document.get("source_unimplemented")
    if not isinstance(source_unimplemented, list) or {
        item.get("branch") for item in source_unimplemented
    } != SOURCE_UNIMPLEMENTED:
        raise VerificationError("source-unimplemented inventory drift")
    branches = document.get("branches")
    if not isinstance(branches, list) or not branches:
        raise VerificationError("branch rows missing")
    for row in branches:
        if not isinstance(row, dict) or not row.get("id") or not row.get("rust") or not row.get("payload"):
            raise VerificationError("branch row lacks executable payload semantics")
    return {"schema": document["schema"], "portable_missing": [], "branch_count": len(branches)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    args = parser.parse_args()
    print(verify(args.matrix))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
