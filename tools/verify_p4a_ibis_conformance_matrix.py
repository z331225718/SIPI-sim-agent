"""Verify the fail-closed P4A IBIS conformance and unsupported boundary."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p4a-ibis-conformance-matrix.v1.yaml"
SCHEMA = "sipi.p4a-ibis-conformance-matrix.v1"
STATUSES = {"implemented_self_tested", "external_profile_accepted", "unsupported", "not_assessed"}
EXTERNAL_IDENTITY = {
    "id": "ibis-org-sample1-input-typ-static-v2",
    "charter_path": "docs/baselines/p4a-ibis-input-typ-static-acceptance.v1.yaml",
    "charter_sha256": "c2f8a900e217a525f0959836a53538501802524ac72ebc7c7fef06e8a3f0fcda",
    "asset_sha256": "46c53a49a31dea27769f0dddddadea72f03f1f956fb8e60aeaa24f83a7201b95",
    "selector_sha256": "0be75aff11736ab3fee529275984551c241433d189ba1a21bad1b0e0e70fd2ff",
    "external_report_sha256": "5814c96e947a2bc059e1fb76e2d44f48e78f80d837bc2ac5506896892c6dcf32",
    "custody": "external_only",
}


class MatrixError(RuntimeError):
    pass


def _relative_reference(value: object) -> bool:
    return (
        isinstance(value, str)
        and value
        and not value.startswith(("/", "\\"))
        and ".." not in value.split("/")
        and not re.match(r"^[A-Za-z]:", value)
    )


def validate(document: object) -> dict:
    if not isinstance(document, dict) or set(document) != {"schema", "status", "selected_external_profile", "entries", "non_claims"}:
        raise MatrixError("matrix_shape_invalid")
    if document["schema"] != SCHEMA or document["status"] != "boundary_recorded":
        raise MatrixError("matrix_status_invalid")
    if document["selected_external_profile"] != EXTERNAL_IDENTITY:
        raise MatrixError("external_profile_identity_invalid")
    entries = document["entries"]
    if not isinstance(entries, list) or not entries:
        raise MatrixError("entries_invalid")
    ids: set[str] = set()
    accepted = 0
    counts = {status: 0 for status in STATUSES}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "scope", "status", "entry_points", "evidence_refs", "non_claim"}:
            raise MatrixError("entry_shape_invalid")
        identifier = entry["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9-]+", identifier) or identifier in ids:
            raise MatrixError("entry_id_invalid")
        ids.add(identifier)
        if not isinstance(entry["scope"], str) or not entry["scope"] or entry["status"] not in STATUSES:
            raise MatrixError("entry_status_or_scope_invalid")
        points = entry["entry_points"]
        references = entry["evidence_refs"]
        if not isinstance(points, list) or not all(isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_]+", item) for item in points):
            raise MatrixError("entry_points_invalid")
        if not isinstance(references, list) or not references or not all(_relative_reference(item) for item in references):
            raise MatrixError("evidence_reference_invalid")
        if not isinstance(entry["non_claim"], str) or not entry["non_claim"]:
            raise MatrixError("entry_non_claim_invalid")
        if entry["status"] in {"unsupported", "not_assessed"} and points:
            raise MatrixError("unsupported_entry_exposes_route")
        if entry["status"] == "external_profile_accepted":
            accepted += 1
            if identifier != "selected-input-typ-static-dc-clamp" or len(points) != 2:
                raise MatrixError("external_acceptance_scope_invalid")
        counts[entry["status"]] += 1
    if accepted != 1 or counts["implemented_self_tested"] < 1 or counts["unsupported"] < 1:
        raise MatrixError("coverage_status_invalid")
    claims = document["non_claims"]
    if not isinstance(claims, list) or len(claims) != 3 or not all(isinstance(item, str) and item for item in claims):
        raise MatrixError("non_claims_invalid")
    return {"valid": True, "status": document["status"], "counts": counts, "external_profile_accepted": accepted}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT)
    args = parser.parse_args()
    try:
        result = validate(yaml.safe_load(args.matrix.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, MatrixError) as error:
        result = {"valid": False, "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
