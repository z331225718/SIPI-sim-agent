"""Fail-closed verifier for the profile-scoped delegated phase amendment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.receiver-delegated-phase-amendment.v1"
PROFILE = "channel-rfm-block-2-current-drive-v1"
EXPECTED_TOP_LEVEL = {
    "schema", "status", "profile_id", "revision", "approved_by", "approved_at_utc",
    "approval_ref", "base_charter", "amendment_spec_ref", "phase_policy", "non_claims",
}
EXPECTED_BASE = {
    "approval_ref": "docs/baselines/channel-rfm-receiver-semantic-approval.v1.yaml",
    "erasure_amendment_ref": "docs/baselines/channel-rfm-receiver-erasure-amendment.v1.yaml",
    "primary_spec_ref": "docs/clean-room/specs/p3b-approved-fixed-receiver.v1.md",
}
EXPECTED_POLICY = {
    "candidate_count": 8,
    "training_symbols": 32,
    "score": "absolute_class_separation",
    "unique_margin_relative": 0.01,
    "unique_winner": "preserve_locked_v1_behavior",
    "ambiguous_contender_floor": "best_score_divided_by_1_01",
    "ambiguous_selection": "lowest_phase_index",
    "ambiguous_phase_selection": "delegated_ambiguous_tie_break",
    "ambiguous_cdr_lock_state": "policy_selected_not_locked",
    "result_scope": "policy_selected_diagnostic",
    "unqualified_status": "cdr_unqualified",
}


def verify(document: object, root: Path = ROOT) -> dict:
    blockers: list[str] = []
    if not isinstance(document, dict) or set(document) != EXPECTED_TOP_LEVEL:
        return {"valid": False, "blockers": ["amendment has unknown or missing fields"]}
    if (
        document["schema"] != SCHEMA
        or document["status"] != "approved_delegated_policy"
        or document["profile_id"] != PROFILE
        or document["revision"] != 2
        or document["approved_by"] != "project_owner_delegated_policy"
        or document["approval_ref"] != "user-delegated-autonomy-2026-08-11"
        or not isinstance(document["approved_at_utc"], str)
        or not document["approved_at_utc"].endswith("Z")
    ):
        blockers.append("delegated approval identity is invalid")
    if document["base_charter"] != EXPECTED_BASE:
        blockers.append("base charter anchors drifted")
    if document["amendment_spec_ref"] != "docs/clean-room/specs/p3b-delegated-phase-selection.v2.md":
        blockers.append("amendment spec anchor drifted")
    elif not (root / document["amendment_spec_ref"]).is_file():
        blockers.append("amendment spec is unavailable")
    if document["phase_policy"] != EXPECTED_POLICY:
        blockers.append("delegated phase policy drifted")
    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or len(non_claims) != 4 or not all(isinstance(value, str) and value for value in non_claims):
        blockers.append("non-claims are incomplete")
    forbidden = " ".join(non_claims).lower()
    if "required-profile acceptance" not in forbidden or "not a clock-recovery lock" not in forbidden:
        blockers.append("non-claims do not preserve the non-lock boundary")
    return {"valid": not blockers, "profile_id": document.get("profile_id"), "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amendment", type=Path, default=ROOT / "docs/baselines/channel-rfm-receiver-delegated-phase-amendment.v1.yaml")
    args = parser.parse_args()
    try:
        report = verify(yaml.safe_load(args.amendment.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
