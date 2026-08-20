"""Fail closed on the P3C-03 profile-compare decision-surface preflight.

The preflight freezes the unselected decision surface (metric profile,
reference binding, tolerance policy) pending the P3C-01 owner decision and
prohibits any profile-compare implementation before that decision. The
verifier cross-binds the charter against the PLAN P3C-01 blocker row, the
release publication compare row, the sibling bathtub preflight charter,
and the PLAN P3C-03b row.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-03-profile-compare-decision-preflight.v1.yaml"
PLAN = ROOT / "PLAN.md"
PUBLICATION = ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml"
SIBLING = ROOT / "docs" / "baselines" / "p3c-02-bathtub-decision-preflight.v1.yaml"
SCHEMA = "sipi.p3c-03.profile-compare-decision-preflight.v1"
BLOCKER = "blocked_missing_metric_profile_semantics_and_accepted_receiver_stage"


class ProfileComparePreflightError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProfileComparePreflightError("document_not_mapping")
    return value


def verify_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ProfileComparePreflightError("schema_invalid")
    if document.get("status") != "c4_metric_profile_selected_oracle_reference_bound":
        raise ProfileComparePreflightError("status_invalid")
    if document.get("decision_surface") != {
        "metric_profile": "selected_c4_com_dB_ICN_mV_ERL_1pct",
        "reference_binding": "bound_p5_06e_matlab_oracle",
        "tolerance_policy": "selected_1pct_relative",
    }:
        raise ProfileComparePreflightError("decision_surface_drift")
    if document.get("blocker_linkage") != {
        "plan_row": "P3C-01",
        "blocker": BLOCKER,
        "publication_blocker": "metric_profile_semantics_not_implemented",
        "sibling_preflight": "docs/baselines/p3c-02-bathtub-decision-preflight.v1.yaml",
    }:
        raise ProfileComparePreflightError("blocker_linkage_drift")
    if document.get("admission") != {
        "profile_compare_implementation": "oracle_reference_bound_compare_executed",
        "product_runtime_invoked": False,
        "release_promoted": False,
    }:
        raise ProfileComparePreflightError("admission_drift")
    claims = document.get("non_claims")
    expected_claims = ["not_a_reference_value_choice", "not_com_parity", "not_oracle_invocation", "not_acceptance_evidence"]
    if not isinstance(claims, list) or claims != expected_claims:
        raise ProfileComparePreflightError("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if BLOCKER not in plan_text:
        raise ProfileComparePreflightError("plan_blocker_missing")
    if "**P3C-03b" not in plan_text:
        raise ProfileComparePreflightError("plan_row_missing")
    publication = load_yaml(PUBLICATION)
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or compare.get("acceptance_state") != "specified":
        raise ProfileComparePreflightError("publication_compare_state_drift")
    if "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise ProfileComparePreflightError("publication_compare_blocker_missing")
    sibling = load_yaml(SIBLING)
    if sibling.get("status") != "bathtub_estimator_and_tolerance_not_frozen_pending_owner_decision":
        raise ProfileComparePreflightError("sibling_preflight_drift")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": document["status"],
        "profile_compare_decision_surface": "c4_selected_oracle_reference_bound",
        "profile_compare_implementation": "oracle_reference_bound_compare_executed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.core))
    except (OSError, ValueError, yaml.YAMLError, ProfileComparePreflightError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())