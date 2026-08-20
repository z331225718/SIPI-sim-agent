"""Verify the signed P7-08 retirement approval record.

The record is the owner decision artifact that, once signed with the immutable
evidence hashes, satisfies the owner_retirement_approval gate of P7-08. It
must be signed: approval_state `owner_approved` with a non-empty approved_by
and a valid ISO-8601 UTC approved_at_utc, and it must reference the exact
replacement-map and drift-gate strategy evidence hashes. The record grants
retirement approval ONLY: the non_claims must stay present and every other
effective gate must remain still_pending (no release approval, no license
clearance, no fresh-machine certification, no profile acceptance, no drift-gate
removal).
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
SCHEMA = "sipi.p7-08.retirement-approval-record.v1"
RECORD = ROOT / "docs" / "baselines" / "p7-08-retirement-approval-record.v1.yaml"

MAP = "docs/baselines/p7-08-path-scoped-replacement-map.v1.yaml"
STRATEGY = "docs/baselines/p7-08-drift-gate-retirement-strategy.v1.yaml"

APPROVAL_STATE = "owner_approved"
APPROVED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

NON_CLAIMS = frozenset({
    "not_a_release_approval",
    "not_a_license_clearance",
    "not_a_fresh_machine_certification",
    "not_a_profile_acceptance",
    "not_a_drift_gate_removal",
})

STILL_PENDING_GATES = frozenset({
    "required_profile_accepted",
    "same_batch_drift_gate_removal",
    "release_license_fresh_machine_gates",
})


class ApprovalRecordError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise ApprovalRecordError("pyyaml_unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ApprovalRecordError("record_not_object")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def validate(root: Path = ROOT) -> dict[str, Any]:
    if not RECORD.is_file():
        raise ApprovalRecordError("record_missing")
    record = load_yaml(RECORD)
    if record.get("schema") != SCHEMA:
        raise ApprovalRecordError("record_schema_invalid")
    if record.get("approval_state") != APPROVAL_STATE:
        raise ApprovalRecordError("record_not_owner_approved")
    approved_by = record.get("approved_by")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise ApprovalRecordError("record_missing_signer")
    approved_at_utc = record.get("approved_at_utc")
    if not isinstance(approved_at_utc, str) or not APPROVED_AT_RE.match(approved_at_utc):
        raise ApprovalRecordError("record_signing_time_invalid")
    for ref_name in ("replacement_map", "drift_gate_strategy"):
        binding = record.get("evidence_bindings", {}).get(ref_name)
        if not isinstance(binding, dict) or not binding.get("path") or not binding.get("sha256"):
            raise ApprovalRecordError(f"binding_missing:{ref_name}")
        expected_path = MAP if ref_name == "replacement_map" else STRATEGY
        if binding["path"] != expected_path:
            raise ApprovalRecordError(f"binding_path_mismatch:{ref_name}")
        if binding["sha256"] != sha256_file(root / expected_path):
            raise ApprovalRecordError(f"binding_hash_mismatch:{ref_name}")
    scope = record.get("approval_scope", {})
    claims = scope.get("non_claims")
    if not isinstance(claims, list) or set(claims) != NON_CLAIMS:
        raise ApprovalRecordError("record_non_claims_drift")
    gates = record.get("effective_gates", {})
    if gates.get("owner_retirement_approval") != "filled_by_this_record":
        raise ApprovalRecordError("record_approval_gate_not_filled")
    for gate_name in STILL_PENDING_GATES:
        if gates.get(gate_name) != "still_pending":
            raise ApprovalRecordError(f"record_gate_drift:{gate_name}")
    if gates.get("per_path_replacement_mapping") != "provided_by_bound_evidence":
        raise ApprovalRecordError("record_mapping_gate_drift")
    return {
        "valid": True,
        "approved": True,
        "approved_by": approved_by,
        "approved_at_utc": approved_at_utc,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ApprovalRecordError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
