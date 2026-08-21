"""Verify that P1-04B owner permission is resolved without promoting assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/p1-04b-comparison-permission-reconciliation.v1.yaml"
FACTS = ROOT / "docs/baselines/p1-legacy-fixture-required-profile-facts.v1.yaml"
LEDGER = ROOT / "docs/baselines/plan-remaining-items-ledger.v1.yaml"
OWNER_REQUEST = ROOT / "docs/baselines/owner-input-request.v1.yaml"
SCHEMA = "sipi.p1-04b.comparison-permission-reconciliation.v1"
FACTS_SHA256 = "3848535dcd03008a8815bd1631f9fea9d8790112c56a3fa401f6821dd9f14596"


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
) -> dict[str, Any]:
    document = _load(DOCUMENT) if document is None else document
    if set(document) != {
        "schema", "status", "authority", "historical_facts", "state",
        "remaining_external_facts", "non_claims", "audit_ref",
    } or document.get("schema") != SCHEMA:
        raise ReconciliationError("document_shape_invalid")
    if document.get("status") != "owner_permission_recorded_external_facts_pending":
        raise ReconciliationError("status_invalid")
    if document.get("authority") != {
        "source": "docs/baselines/owner-input-request.v1.yaml",
        "decision": "external fixtures are globally trusted; do not block comparison",
    }:
        raise ReconciliationError("authority_invalid")
    if document.get("historical_facts") != {
        "path": "docs/baselines/p1-legacy-fixture-required-profile-facts.v1.yaml",
        "sha256": FACTS_SHA256,
    } or hashlib.sha256(FACTS.read_bytes()).hexdigest() != FACTS_SHA256:
        raise ReconciliationError("facts_binding_invalid")
    expected_state = {
        "comparison_permission_decided": True,
        "blocker_class": "external_asset_oracle",
        "required_profile_selected": False,
        "required_profile_accepted": False,
        "distribution_authorized": False,
        "product_input_admitted": False,
        "runtime_admitted": False,
        "release_admitted": False,
    }
    if document.get("state") != expected_state:
        raise ReconciliationError("state_promotion_or_drift")
    if document.get("remaining_external_facts") != [
        "exact_selected_profile", "external_custody_identity", "consumption_and_distribution_rights"
    ]:
        raise ReconciliationError("remaining_facts_invalid")
    if set(document.get("non_claims", [])) != {
        "trusted_for_external_comparison_is_not_redistribution_permission",
        "trusted_for_external_comparison_is_not_product_or_runtime_admission",
        "required_by_labels_are_not_profile_selection",
        "no_license_or_release_conclusion",
    }:
        raise ReconciliationError("non_claims_invalid")
    if document.get("audit_ref") != "docs/baselines/audits/2026-08-21-p1-04b-comparison-permission-reconciliation.md" or not (ROOT / document["audit_ref"]).is_file():
        raise ReconciliationError("audit_ref_invalid")

    ledger = _load(LEDGER) if ledger is None else ledger
    row = next((item for item in ledger.get("items", []) if item.get("id") == "P1-04B"), None)
    if not isinstance(row, dict) or row.get("blocker") != "external_asset_oracle" or "tools/verify_p1_04b_comparison_permission_reconciliation.py" not in row.get("gate", []):
        raise ReconciliationError("ledger_state_invalid")
    owner_request = _load(OWNER_REQUEST) if owner_request is None else owner_request
    entry = next((item for item in owner_request.get("entries", []) if item.get("id") == "P1-04B"), None)
    if not isinstance(entry, dict) or entry.get("kind") != "external_asset" or entry.get("decision") != document["authority"]["decision"]:
        raise ReconciliationError("owner_request_state_invalid")
    return {"schema": SCHEMA, "valid": True, "comparison_permission_decided": True, "external_facts_pending": True}


def main() -> int:
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ReconciliationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
