"""Verify that P7-08 owner approval is resolved while release gates stay pending."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import verify_p7_08_retirement_approval_record as approval_gate

DOCUMENT = ROOT / "docs/baselines/p7-08-owner-decision-reconciliation.v1.yaml"
APPROVAL = ROOT / "docs/baselines/p7-08-retirement-approval-record.v1.yaml"
LEDGER = ROOT / "docs/baselines/plan-remaining-items-ledger.v1.yaml"
OWNER_REQUEST = ROOT / "docs/baselines/owner-input-request.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p7-08.owner-decision-reconciliation.v1"
APPROVAL_SHA256 = "3fdc41a119fd4caf0f434ed9b4dcb04e553b8e411521467704dfbeb4d7b430df"


class ReconciliationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReconciliationError("document_not_mapping")
    return value


def validate(
    document: dict[str, Any] | None = None,
    *,
    ledger: dict[str, Any] | None = None,
    owner_request: dict[str, Any] | None = None,
    plan_text: str | None = None,
) -> dict[str, Any]:
    document = _load(DOCUMENT) if document is None else document
    if set(document) != {"schema", "status", "approval_record", "state", "non_claims", "audit_ref"} or document.get("schema") != SCHEMA:
        raise ReconciliationError("document_shape_invalid")
    if document.get("status") != "owner_retirement_approval_resolved_release_gates_pending":
        raise ReconciliationError("status_invalid")
    if document.get("approval_record") != {
        "path": "docs/baselines/p7-08-retirement-approval-record.v1.yaml",
        "sha256": APPROVAL_SHA256,
        "approval_state": "owner_approved",
    } or hashlib.sha256(APPROVAL.read_bytes()).hexdigest() != APPROVAL_SHA256:
        raise ReconciliationError("approval_binding_invalid")
    try:
        result = approval_gate.validate(ROOT)
    except approval_gate.ApprovalRecordError as error:
        raise ReconciliationError("approval_record_invalid") from error
    if result.get("approved") is not True:
        raise ReconciliationError("approval_record_invalid")
    expected_state = {
        "blocker_class": "release_gate",
        "owner_input_requested": False,
        "owner_retirement_approval": "satisfied",
        "required_profile_accepted": False,
        "same_batch_drift_gate_removal": False,
        "release_license_fresh_machine_gates": False,
        "path_deletion_performed": False,
        "drift_gate_removed": False,
        "release_admitted": False,
    }
    if document.get("state") != expected_state:
        raise ReconciliationError("state_promotion_or_drift")
    if set(document.get("non_claims", [])) != {
        "retirement_plan_approval_is_not_path_deletion",
        "retirement_plan_approval_is_not_profile_acceptance",
        "retirement_plan_approval_is_not_license_or_fresh_machine_clearance",
        "retirement_plan_approval_is_not_release_promotion",
    }:
        raise ReconciliationError("non_claims_invalid")
    if document.get("audit_ref") != "docs/baselines/audits/2026-08-21-p7-08-owner-decision-reconciliation.md" or not (ROOT / document["audit_ref"]).is_file():
        raise ReconciliationError("audit_ref_invalid")

    ledger = _load(LEDGER) if ledger is None else ledger
    row = next((item for item in ledger.get("items", []) if item.get("id") == "P7-08"), None)
    if not isinstance(row, dict) or row.get("blocker") != "release_gate" or "tools/verify_p7_08_owner_decision_reconciliation.py" not in row.get("gate", []):
        raise ReconciliationError("ledger_state_invalid")
    owner_request = _load(OWNER_REQUEST) if owner_request is None else owner_request
    if any(item.get("id") == "P7-08" for item in owner_request.get("entries", [])):
        raise ReconciliationError("owner_request_stale")
    plan_text = PLAN.read_text(encoding="utf-8") if plan_text is None else plan_text
    if "**P7-08d** owner-decision reconciliation" not in plan_text or "approval_state pending_owner_signature" in plan_text:
        raise ReconciliationError("plan_state_invalid")
    return {"schema": SCHEMA, "valid": True, "owner_approval_resolved": True, "release_gates_pending": True}


def main() -> int:
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ReconciliationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
