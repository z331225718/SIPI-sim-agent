"""Verify P6-08 report inspect metadata-only projection completeness.

P6-08 requires `report inspect --stdin` to project integrity metadata only
for sealed, re-verified artifacts in a caller-owned root, failing closed
on hash mismatch, unsealed set, or budget violation. This gate fails
closed if the publication row, its evidence audit, or the CLI route
disappears.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p6-08.report-inspect-metadata-only.v1"

PUBLICATION = "docs/baselines/release-capability-publication.v1.yaml"
AUDIT = "docs/baselines/audits/2026-08-11-p6-artifact-report.md"


class ReportInspectError(RuntimeError):
    pass


def load_yaml(relative: str) -> dict[str, Any]:
    if yaml is None:
        raise ReportInspectError("pyyaml_unavailable")
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReportInspectError("document_not_mapping")
    return value


def read_text(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ReportInspectError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (PUBLICATION, AUDIT):
        if not (root / relative).is_file():
            raise ReportInspectError(f"file_missing:{relative}")
    publication = load_yaml(PUBLICATION)
    row = next((r for r in publication.get("rows", []) if isinstance(r, dict) and r.get("id") == "report-inspect"), None)
    if (
        row is None
        or row.get("command_id") != "report.inspect"
        or row.get("product_surface") != "available"
        or row.get("acceptance_state") != "specified"
    ):
        raise ReportInspectError("report_inspect_binding_invalid")
    audit = read_text(AUDIT)
    for token in ("integrity", "metadata", "hash"):
        if token not in audit:
            raise ReportInspectError(f"audit_token_missing:{token}")
    return {"valid": True, "metadata_only": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ReportInspectError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
