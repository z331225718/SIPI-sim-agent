"""Fail closed on the owner-approved P3C PRBS9 sampled-eye and TIE core."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-prbs9-metric-core.v2.yaml"
CONTRACT = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v2.yaml"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-prbs9-metric-core.v2"
CONTRACT_SHA256 = "f47329b6ddda01cbcde1f24e21cb93e03f8ef6139ea2d43ff74cad9e2049d2b5"


class CoreError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CoreError("document_not_mapping")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def implementation_source(root: Path) -> str:
    return (root / "crates/sipi-compare/src/prbs9_waveform_v2.rs").read_text(encoding="utf-8")


def verify_document(document: object, *, root: Path = ROOT) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "product_owned_strict_grid_waveform_eye_tie_core_specified_not_profile_accepted":
        raise CoreError("schema_or_status_invalid")
    if sha256_file(root / CONTRACT.relative_to(ROOT)) != CONTRACT_SHA256:
        raise CoreError("contract_source_drift")
    if document.get("contract_binding") != {"contract_v2_content_sha256": CONTRACT_SHA256, "supersedes_nrmse_core_v1_as_current_implementation": True}:
        raise CoreError("contract_binding_drift")
    expected_profile = {
        "total_samples": 49056,
        "compared_sample_range": [32704, 49056],
        "samples_per_ui": 32,
        "waveform_nrmse_limit": 0.01,
        "eye": {"phase": "sample_index_modulo_32", "partition": "frozen_prbs9_current_ui", "opening": "min_high_minus_max_low", "width_center_phase": 16, "width": "contiguous_positive_bins_containing_center_times_dt", "wraparound": "prohibited", "interpolation": "prohibited", "relative_error_limit": 0.01, "zero_reference_metric": "reject"},
        "tie": {"nominal_transition_window": "left_closed_right_open_plus_or_minus_half_ui", "rising_crossing": "left_negative_right_nonnegative", "falling_crossing": "left_positive_right_nonpositive", "interpolation": "linear_between_adjacent_samples", "matching": "same_ideal_transition_index_only", "crossings_per_window": "exactly_one_or_reject", "zero_plateau": "reject", "tie_mean_removal": "prohibited", "paired_rmse_limit_seconds": 3.125e-13},
    }
    if document.get("profile") != expected_profile:
        raise CoreError("profile_semantics_drift")
    if document.get("input_boundary") != {"scope": "caller_supplied_strict_grid_waveforms_only", "requires_full_three_period_finite_waveforms": True, "reads_external_assets": False, "external_reference_binding": "not_evaluated"}:
        raise CoreError("input_boundary_drift")
    if document.get("implementation") != {"crate": "sipi-compare", "module": "prbs9_waveform_v2", "public_entrypoint": "compare_prbs9_metrics_v2", "policy": "sipi.compare.prbs9-v2.third-period-strict-grid-nrmse.v1"}:
        raise CoreError("implementation_scope_drift")
    expected_admission = {"candidate_waveform_eye_jitter_acceptance_evaluated": False, "accepted_receiver": False, "acceptance_ready": False, "promotion_eligible": False, "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False, "release_ledger_promoted": False}
    if document.get("admission") != expected_admission:
        raise CoreError("admission_gate_drift")
    publication = json.loads((root / PUBLICATION.relative_to(ROOT)).read_text(encoding="utf-8"))
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or compare.get("acceptance_state") != "specified" or "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise CoreError("release_compare_metric_gate_drift")
    source = implementation_source(root)
    required_tokens = (
        CONTRACT_SHA256,
        "PRBS9_PERIOD_SHA256_V2",
        "PRBS9_EYE_RELATIVE_ERROR_LIMIT_V2: f64 = 0.01",
        "PRBS9_TIE_ERROR_LIMIT_SECONDS_V2: f64 = 3.125e-13",
        "pub fn compare_prbs9_metrics_v2",
        "fn eye_metric",
        "while first > 0 && openings[first - 1] > 0.0",
        "while last + 1 < SAMPLES_PER_UI && openings[last + 1] > 0.0",
        "left < 0.0 && right >= 0.0",
        "left > 0.0 && right <= 0.0",
        "ZeroPlateau",
        "CrossingCount",
        "caller_supplied_strict_grid_waveforms_only",
        "external_reference_binding: \"not_evaluated\"",
    )
    if any(token not in source for token in required_tokens):
        raise CoreError("implementation_binding_drift")
    return {"schema": SCHEMA, "status": document["status"], "metric_core": "specified", "historical_nrmse_core": "source_drift_preserved", "external_reference_binding": "not_evaluated", "release_promoted": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.core))
    except (OSError, ValueError, yaml.YAMLError, CoreError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
