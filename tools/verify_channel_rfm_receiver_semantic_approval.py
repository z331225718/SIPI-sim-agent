"""Verify the immutable owner approval record for the fixed receiver charter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "docs/baselines/channel-rfm-receiver-semantic-approval.v1.yaml"
REQUIRED = {
    "schema", "status", "profile_id", "approved_by", "approved_at", "approval_ref",
    "proposal_anchor", "approved_spec", "external_compare_status", "non_claims",
}


def verify_document(document: object, root: Path = ROOT) -> dict:
    if not isinstance(document, dict) or set(document) != REQUIRED:
        return {"valid": False, "blockers": ["approval has unknown or missing fields"]}
    blockers: list[str] = []
    if document["schema"] != "sipi.channel.receiver-semantic-approval.v1" or document["status"] != "approved_owner_semantics":
        blockers.append("approval identity is invalid")
    if document["profile_id"] != "channel-rfm-block-2-current-drive-v1" or document["approved_by"] != "user":
        blockers.append("approval owner or profile is invalid")
    anchor = document["proposal_anchor"]
    if not isinstance(anchor, dict) or set(anchor) != {"commit", "charter_path", "charter_blob", "spec_path", "spec_blob"}:
        blockers.append("proposal anchor is incomplete")
    elif anchor != {
        "commit": "c7a2ded",
        "charter_path": "docs/baselines/channel-rfm-receiver-semantic-charter.v1.yaml",
        "charter_blob": "d148bc34e873cf498ef6c636c016a2768692d9c9",
        "spec_path": "docs/clean-room/specs/p3b-receiver-semantic-charter.v1.md",
        "spec_blob": "3194542cf4089a4fdf3f3c2cb8710d49eb267a88",
    }:
        blockers.append("proposal anchor drifted")
    spec = document["approved_spec"]
    if spec != {"path": "docs/clean-room/specs/p3b-approved-fixed-receiver.v1.md", "status": "fixed_data_aided_receiver_v1"} or not (root / spec.get("path", "")).is_file():
        blockers.append("approved fixed receiver specification is unavailable")
    if document["external_compare_status"] not in {"blocked_missing_authorized_reference_bit_source", "authorized_source_attested_pending_receiver_compare"}:
        blockers.append("external comparison status is unsafe")
    if not isinstance(document["non_claims"], list) or len(document["non_claims"]) < 3:
        blockers.append("approval non-claims are incomplete")
    return {"valid": not blockers, "status": document.get("status"), "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", type=Path, default=APPROVAL)
    args = parser.parse_args()
    if yaml is None:
        print(json.dumps({"valid": False, "blockers": ["pyyaml is unavailable"]}), file=sys.stderr)
        return 2
    try:
        value = yaml.safe_load(args.approval.read_text(encoding="utf-8"))
    except OSError as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}), file=sys.stderr)
        return 2
    report = verify_document(value)
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
