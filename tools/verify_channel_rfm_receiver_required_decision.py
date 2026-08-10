"""Verify the user-required RFM receiver decision remains scope-limited."""

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
SCHEMA = "sipi.channel.receiver-required-decision.v1"
PROFILE_ID = "channel-rfm-block-2-current-drive-v1"
REQUIRED_BY = "user-confirmed-2026-08-10-channel-rfm-receiver"
STATUS = "required_blocked_missing_receiver_semantics"
CURRENT_STATUSES = {STATUS, "required_blocked_missing_authorized_reference_bit_source"}


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("required decision must be a YAML object")
    return value


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _profile(inventory: object) -> dict | None:
    if not isinstance(inventory, dict) or not isinstance(inventory.get("profiles"), list):
        return None
    return next((item for item in inventory["profiles"] if isinstance(item, dict) and item.get("id") == PROFILE_ID), None)


def verify_document(decision: object, inventory: object, readiness: object) -> dict:
    blockers: list[str] = []
    required = {"schema", "profile_id", "decision", "decision_ref", "receiver_status", "scope", "non_claims"}
    if not _exact(decision, required):
        return {"valid": False, "blockers": ["decision has unknown or missing fields"]}
    if decision["schema"] != SCHEMA or decision["profile_id"] != PROFILE_ID or decision["decision"] != "required" or decision["decision_ref"] != REQUIRED_BY or decision["receiver_status"] != STATUS or decision["scope"] != "single_rfm_current_drive_receiver_profile":
        blockers.append("decision identity or scope is invalid")
    if not isinstance(decision["non_claims"], list) or len(decision["non_claims"]) < 3 or not all(isinstance(item, str) and item for item in decision["non_claims"]):
        blockers.append("decision non-claims are incomplete")
    profile = _profile(inventory)
    acceptance = profile.get("acceptance") if isinstance(profile, dict) else None
    if not isinstance(acceptance, dict) or profile.get("boundary") != "oracle_only" or acceptance.get("status") not in CURRENT_STATUSES or acceptance.get("required_by") != REQUIRED_BY:
        blockers.append("inventory does not carry the same scope-limited required decision")
    if not isinstance(readiness, dict) or readiness.get("status") != "required_selected_missing_receiver_semantics" or readiness.get("candidate_profile_id") != PROFILE_ID or readiness.get("owner_decision") != {"required_by": REQUIRED_BY, "decision": "required"}:
        blockers.append("readiness record does not carry the same required decision")
    return {"valid": not blockers, "profile_id": PROFILE_ID, "receiver_status": STATUS, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", type=Path, default=ROOT / "docs/baselines/channel-rfm-receiver-required-decision.v1.yaml")
    parser.add_argument("--inventory", type=Path, default=ROOT / "acceptance-profiles.v1.yaml")
    parser.add_argument("--readiness", type=Path, default=ROOT / "docs/baselines/channel-rfm-receiver-readiness.v1.yaml")
    args = parser.parse_args()
    try:
        report = verify_document(_load(args.decision), _load(args.inventory), _load(args.readiness))
    except (OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
