"""Verify the exact external-only P4A-01 official-object rights recheck."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/p4a-01-official-object-rights-recheck.v1.yaml"
PREDECESSOR = ROOT / "docs/baselines/p4a-01-selected-ibis-truncation-disposition.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p4a-01-official-object-rights-recheck.md"
OFFICIAL_SOURCE = Path(r"C:\Users\z3312\code\.sipi-p4a-official-asset-20260821\as4c512m16md4v-053bin.ibs")
SCHEMA = "sipi.p4a-01.official-object-rights-recheck.v1"
PREDECESSOR_SHA256 = "dbc1072584528cc9ae722eaa022b7548e4244799f2726f7f6d420a2c64902f0f"
ASSET_SHA256 = "53e27609dbb81e7685456a48c611111fed34ca14477623e46a9a9a582a7a646b"


class RightsRecheckError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RightsRecheckError("manifest_not_mapping")
    return value


def block_hash(lines: list[str], start: int, end: int) -> str:
    return sha256("\n".join(lines[start - 1 : end]).encode("ascii"))


def validate(root: Path = ROOT, official_source: Path = OFFICIAL_SOURCE) -> dict[str, Any]:
    manifest = load_yaml(root / MANIFEST.relative_to(ROOT))
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "exact_identity_revalidated_external_only_rights_unverified":
        raise RightsRecheckError("schema_or_status_drift")
    if manifest.get("promotion_eligible") is not False:
        raise RightsRecheckError("promotion_boundary_drift")
    predecessor = manifest.get("predecessor", {})
    if predecessor != {"path": PREDECESSOR.relative_to(ROOT).as_posix(), "sha256": PREDECESSOR_SHA256, "unchanged": True}:
        raise RightsRecheckError("predecessor_binding_drift")
    if sha256((root / PREDECESSOR.relative_to(ROOT)).read_bytes()) != PREDECESSOR_SHA256:
        raise RightsRecheckError("predecessor_hash_drift")

    data = official_source.read_bytes()
    identity = manifest.get("identity", {})
    if len(data) != identity.get("byte_length") or sha256(data) != identity.get("sha256") or sha256(data) != ASSET_SHA256:
        raise RightsRecheckError("official_identity_drift")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise RightsRecheckError("official_asset_not_ascii") from error
    lines = text.splitlines()
    notices = manifest.get("embedded_notices", {})
    for name in ("source_block", "disclaimer_block", "copyright_block"):
        spec = notices.get(name, {})
        span = spec.get("line_span")
        if not isinstance(span, list) or len(span) != 2 or block_hash(lines, span[0], span[1]) != spec.get("normalized_text_sha256"):
            raise RightsRecheckError(f"{name}_drift")
    marker_counts = {
        "explicit_license_marker_count": len(re.findall(r"(?i)\blicen[cs]e\b", text)),
        "explicit_permission_marker_count": len(re.findall(r"(?i)\bpermission\b", text)),
        "explicit_redistribution_marker_count": len(re.findall(r"(?i)\bredistribut\w*\b", text)),
    }
    for field, count in marker_counts.items():
        if notices.get(field) != count:
            raise RightsRecheckError(f"{field}_drift")
    disclaimer = "\n".join(lines[17:21]).lower()
    copyright_line = lines[21].lower()
    if "customers may only modify" not in disclaimer or notices.get("disclaimer_block", {}).get("customer_application_modification_statement_present") is not True:
        raise RightsRecheckError("modification_statement_drift")
    if "all rights reserved" not in copyright_line or notices.get("copyright_block", {}).get("all_rights_reserved_present") is not True:
        raise RightsRecheckError("copyright_boundary_drift")

    transport = manifest.get("transport_recheck", {})
    if transport.get("download_status") != 200 or transport.get("content_length") != len(data) or transport.get("fresh_retrieval_identity_match") is not True:
        raise RightsRecheckError("transport_recheck_drift")
    rights = manifest.get("rights_disposition", {})
    if rights.get("rights_status") != "unverified" or rights.get("external_identity_observation_authorized") is not True:
        raise RightsRecheckError("rights_status_drift")
    for field in ("modification_statement_is_redistribution_permission", "product_source_use_authorized", "redistribution_authorized"):
        if rights.get(field) is not False:
            raise RightsRecheckError(f"rights_boundary_drift:{field}")
    custody = manifest.get("custody", {})
    if custody.get("complete_bytes") != "external_operator_only" or custody.get("complete_bytes_present_in_worktree") is not False:
        raise RightsRecheckError("custody_boundary_drift")
    for candidate in root.rglob("*.ibs"):
        candidate_data = candidate.read_bytes()
        if len(candidate_data) == len(data) and sha256(candidate_data) == ASSET_SHA256:
            raise RightsRecheckError("complete_official_bytes_present_in_worktree")

    audit = manifest.get("audit", {})
    if audit.get("path") != AUDIT.relative_to(ROOT).as_posix():
        raise RightsRecheckError("audit_path_drift")
    audit_path = root / Path(audit["path"])
    if sha256(audit_path.read_bytes()) != audit.get("sha256"):
        raise RightsRecheckError("audit_hash_drift")
    for token in ("# P4A-01 Official Object Rights Recheck", "no explicit\nlicense", "not legal advice"):
        if token not in audit_path.read_text(encoding="utf-8"):
            raise RightsRecheckError("audit_content_drift")
    return {"schema": SCHEMA, "valid": True, "status": manifest["status"], "byte_length": len(data), "sha256": sha256(data)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--official-source", type=Path, default=OFFICIAL_SOURCE)
    args = parser.parse_args()
    try:
        report = validate(args.root, args.official_source)
    except (OSError, yaml.YAMLError, RightsRecheckError) as error:
        report = {"schema": SCHEMA, "valid": False, "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
