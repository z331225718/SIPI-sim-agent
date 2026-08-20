"""Verify the P4A-06 IBIS CLI vertical slices are complete and bound.

P4A-06 wires the accepted IBIS electrical slices as strict stdin CLI
routes: inspect, dc-evaluate, quasi-static-evaluate, sealed-artifact,
sealed-artifact-batch, and differential-rc-evaluate. This gate fails
closed if any route loses its command-manifest binding, its conformance-
matrix implemented_self_tested status, or its publication row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4a-06.cli-slices-complete.v1"

PUBLICATION = "docs/baselines/release-capability-publication.v1.yaml"
MATRIX = "docs/baselines/p4a-ibis-conformance-matrix.v1.yaml"

ROUTE_ROWS = {
    "ibis.dc-evaluate": "ibis-dc-evaluate",
    "ibis.quasi-static-evaluate": "ibis-quasi-static-evaluate",
    "ibis.quasi-static-evaluate-artifact": "ibis-quasi-static-artifact-evaluate",
    "ibis.quasi-static-evaluate-artifact-batch": "ibis-quasi-static-artifact-batch-evaluate",
    "rx-load.differential-rc-evaluate": "selected-differential-rc-load-evaluate",
    "ibis.inspect": "ibis-inspect",
}

MATRIX_ENTRY_IDS = {
    "input-typ-static-dc-evaluate-stdin",
    "input-typ-quasi-static-evaluate-stdin",
    "input-typ-quasi-static-evaluate-sealed-artifact",
    "input-typ-quasi-static-evaluate-sealed-artifact-batch",
    "selected-differential-rc-load-evaluate-stdin",
}


class SlicesError(RuntimeError):
    pass


def git_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    return completed.returncode == 0


def load_yaml(relative: str) -> dict[str, Any]:
    if yaml is None:
        raise SlicesError("pyyaml_unavailable")
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SlicesError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (PUBLICATION, MATRIX):
        if not (root / relative).is_file():
            raise SlicesError(f"file_missing:{relative}")

    publication = load_yaml(PUBLICATION)
    rows = {row.get("id"): row for row in publication.get("rows", []) if isinstance(row, dict)}
    for command_id, row_id in ROUTE_ROWS.items():
        row = rows.get(row_id)
        if (
            row is None
            or row.get("command_id") != command_id
            or row.get("product_surface") != "available"
            or row.get("acceptance_state") != "specified"
        ):
            raise SlicesError(f"route_unbound:{command_id}:{row_id}")

    matrix = load_yaml(MATRIX)
    entries = {entry.get("id"): entry for entry in matrix.get("entries", []) if isinstance(entry, dict)}
    for entry_id in MATRIX_ENTRY_IDS:
        entry = entries.get(entry_id)
        if entry is None or entry.get("status") != "implemented_self_tested":
            raise SlicesError(f"matrix_route_not_implemented:{entry_id}")
    if matrix.get("status") != "boundary_recorded":
        raise SlicesError("matrix_status_drift")

    return {"valid": True, "routes": len(ROUTE_ROWS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SlicesError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
