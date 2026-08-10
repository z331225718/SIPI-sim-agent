"""Verify the owner-approved erasure feedback amendment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"schema", "status", "profile_id", "approved_by", "approved_at", "approval_ref", "base_approval_anchor", "amendment_spec", "non_claims"}


def verify_document(value: object, root: Path = ROOT) -> dict:
    if not isinstance(value, dict) or set(value) != REQUIRED:
        return {"valid": False, "blockers": ["amendment has unknown or missing fields"]}
    blockers: list[str] = []
    if value["schema"] != "sipi.channel.receiver-semantic-amendment.v1" or value["status"] != "approved_owner_semantics" or value["profile_id"] != "channel-rfm-block-2-current-drive-v1" or value["approved_by"] != "user":
        blockers.append("amendment identity is invalid")
    if value["base_approval_anchor"] != {
        "commit": "82c7e90",
        "approval_path": "docs/baselines/channel-rfm-receiver-semantic-approval.v1.yaml",
        "approval_blob": "481a8eb57f320e3a8b1fa7af669162026634403f",
        "spec_path": "docs/clean-room/specs/p3b-approved-fixed-receiver.v1.md",
        "spec_blob": "1cb39562d28ad67d01dc28804178641b365ad1e9",
    }:
        blockers.append("base approval anchor drifted")
    amendment = value["amendment_spec"]
    if amendment != {
        "path": "docs/clean-room/specs/p3b-approved-fixed-receiver-erasure-amendment.v1.md",
        "erasure_feedback_symbol": 0.0,
        "continue_after_erasure": True,
        "erasure_counts_as_error": True,
    } or not (root / amendment.get("path", "")).is_file():
        blockers.append("erasure amendment semantics are invalid")
    if not isinstance(value["non_claims"], list) or len(value["non_claims"]) < 3:
        blockers.append("amendment non-claims are incomplete")
    return {"valid": not blockers, "status": value.get("status"), "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amendment", type=Path, default=ROOT / "docs/baselines/channel-rfm-receiver-erasure-amendment.v1.yaml")
    args = parser.parse_args()
    try:
        value = yaml.safe_load(args.amendment.read_text(encoding="utf-8"))
    except OSError as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}), flush=True)
        return 2
    report = verify_document(value)
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
