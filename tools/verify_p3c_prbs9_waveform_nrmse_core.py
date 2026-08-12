"""Fail closed on the narrow P3C PRBS9 waveform-NRMSE core boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-prbs9-waveform-nrmse-core.v1.yaml"
CONTRACT = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v2.yaml"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-prbs9-waveform-nrmse-core.v1"
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
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "product_owned_strict_grid_waveform_nrmse_specified_not_profile_accepted":
        raise CoreError("schema_or_status_invalid")
    if sha256_file(root / CONTRACT.relative_to(ROOT)) != CONTRACT_SHA256 or document.get("contract_binding") != {"contract_v2_content_sha256": CONTRACT_SHA256}:
        raise CoreError("contract_source_drift")
    if document.get("profile") != {"total_samples": 49056, "compared_start": 32704, "compared_samples": 16352, "waveform_nrmse_limit": 0.01, "formula": "sqrt(sum((candidate-reference)^2)/sum(reference^2))", "alignment": "prohibited", "resampling": "prohibited", "gain_fit": "prohibited", "dc_removal": "prohibited", "polarity_flip": "prohibited", "zero_reference_norm": "reject"}:
        raise CoreError("profile_semantics_drift")
    if document.get("input_boundary") != {"scope": "caller_supplied_strict_grid_waveforms_only", "requires_full_three_period_finite_waveforms": True, "reads_external_assets": False, "external_reference_binding": "not_evaluated"}:
        raise CoreError("input_boundary_drift")
    if document.get("implementation") != {"crate": "sipi-compare", "module": "prbs9_waveform_v2", "public_entrypoint": "compare_prbs9_waveform_nrmse_v2", "policy": "sipi.compare.prbs9-v2.third-period-strict-grid-nrmse.v1", "eye_metrics": "not_implemented", "jitter_metrics": "not_implemented"}:
        raise CoreError("implementation_scope_drift")
    expected_admission = {"candidate_waveform_eye_jitter_acceptance_evaluated": False, "accepted_receiver": False, "acceptance_ready": False, "promotion_eligible": False, "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False, "release_ledger_promoted": False}
    if document.get("admission") != expected_admission:
        raise CoreError("admission_gate_drift")
    publication = json.loads((root / PUBLICATION.relative_to(ROOT)).read_text(encoding="utf-8"))
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or compare.get("acceptance_state") != "specified" or "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise CoreError("release_compare_metric_gate_drift")
    source = implementation_source(root)
    for token in (CONTRACT_SHA256, "PRBS9_TOTAL_SAMPLES_V2: usize = 49_056", "PRBS9_THIRD_PERIOD_START_V2: usize = 32_704", "PRBS9_THIRD_PERIOD_SAMPLES_V2: usize = 16_352", "PRBS9_WAVEFORM_NRMSE_LIMIT_V2: f64 = 0.01", "caller_supplied_strict_grid_waveforms_only", "external_reference_binding: \"not_evaluated\"", "eye_metrics: \"not_implemented\"", "jitter_metrics: \"not_implemented\""):
        if token not in source:
            raise CoreError("implementation_binding_drift")
    return {"schema": SCHEMA, "status": document["status"], "waveform_nrmse_core": "specified", "external_reference_binding": "not_evaluated", "release_promoted": False}


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
