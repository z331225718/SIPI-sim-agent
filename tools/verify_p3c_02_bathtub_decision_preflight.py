"""Fail closed on the P3C-02 bathtub/BER decision-surface preflight.

The preflight freezes the unselected decision surface (estimator, tolerance,
reference binding, eye folding/bins) pending the P3C-01 owner decision and
prohibits any bathtub implementation before that decision. The verifier
cross-binds the charter against the PLAN P3C-01 blocker row, the metric
core v2 charter blockers, the release publication compare row, and the
PLAN P3C-02d row.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-02-bathtub-decision-preflight.v1.yaml"
PLAN = ROOT / "PLAN.md"
CORE_CHARTER = ROOT / "docs" / "baselines" / "p3c-prbs9-metric-core.v2.yaml"
PUBLICATION = ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-02.bathtub-decision-preflight.v1"
BLOCKER = "blocked_missing_metric_profile_semantics_and_accepted_receiver_stage"


class BathtubPreflightError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BathtubPreflightError("document_not_mapping")
    return value


def verify_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise BathtubPreflightError("schema_invalid")
    if document.get("status") != "bathtub_estimator_and_tolerance_not_frozen_pending_owner_decision":
        raise BathtubPreflightError("status_invalid")
    if document.get("decision_surface") != {
        "estimator": "unselected_pending_owner_decision",
        "tolerance": "unselected_pending_owner_decision",
        "reference_binding": "unselected_pending_owner_decision",
        "eye_folding_bins": "unselected_pending_owner_decision",
    }:
        raise BathtubPreflightError("decision_surface_drift")
    if document.get("blocker_linkage") != {
        "plan_row": "P3C-01",
        "blocker": BLOCKER,
        "core_charter_blocker": "statistical_eye_contour_semantics_missing",
        "publication_blocker": "metric_profile_semantics_not_implemented",
    }:
        raise BathtubPreflightError("blocker_linkage_drift")
    if document.get("admission") != {
        "bathtub_implementation": "prohibited_without_owner_decision",
        "estimator_introduced": False,
        "product_runtime_invoked": False,
        "release_promoted": False,
    }:
        raise BathtubPreflightError("admission_drift")
    claims = document.get("non_claims")
    expected_claims = ["not_an_estimator_choice", "not_a_tolerance_choice", "not_com_parity", "not_acceptance_evidence"]
    if not isinstance(claims, list) or claims != expected_claims:
        raise BathtubPreflightError("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if BLOCKER not in plan_text:
        raise BathtubPreflightError("plan_blocker_missing")
    if "**P3C-02d" not in plan_text:
        raise BathtubPreflightError("plan_row_missing")
    core = load_yaml(CORE_CHARTER)
    blockers = core.get("blockers")
    if not isinstance(blockers, list) or "statistical_eye_contour_semantics_missing" not in blockers:
        raise BathtubPreflightError("core_charter_blocker_missing")
    publication = load_yaml(PUBLICATION)
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or compare.get("acceptance_state") != "specified":
        raise BathtubPreflightError("publication_compare_state_drift")
    if "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise BathtubPreflightError("publication_compare_blocker_missing")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": document["status"],
        "bathtub_decision_surface": "frozen_unselected",
        "bathtub_implementation": "prohibited",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.core))
    except (OSError, ValueError, yaml.YAMLError, BathtubPreflightError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
