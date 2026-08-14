"""Verify the fixed IEEE BSD truncation direct-port boundary."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-truncation-direct-port.v1.yaml"


class DirectPortError(ValueError):
    pass


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != "sipi.p3c-ieee-bsd-truncation-direct-port.v1" or document.get("status") != "selected_ieee_bsd3_truncation_implemented_external_observation_pending":
        raise DirectPortError("truncation_direct_port_schema_invalid")
    source = document.get("source")
    if not isinstance(source, dict) or source.get("git_blob") != "f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3" or source.get("content_sha256") != "b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0" or source.get("license") != "BSD-3-Clause" or source.get("included_upstream_lines") != [96, 102] or source.get("excluded_source_objects") != ["ieee-802-com-causality-delay-bsd3-v1"]:
        raise DirectPortError("truncation_source_boundary_invalid")
    policy = document.get("policy")
    if not isinstance(policy, dict) or policy.get("input_type") != "sipi_ieee_com_sparam::SelectedP3cCausalResponseV1" or policy.get("threshold") != 1.0e-3 or policy.get("crossing") != "last_absolute_sample_strictly_greater_than_peak_times_threshold" or policy.get("retained_interval") != "zero_based_half_open_zero_to_last_crossing_plus_one" or policy.get("preserve_leading_samples") is not True or policy.get("preserve_sample_interval") is not True or policy.get("delay_extraction") != "prohibited" or policy.get("time_shift") != "prohibited" or policy.get("normalization") != "prohibited" or policy.get("input_sample_limit") != 51200 or policy.get("caller_overrides") != "prohibited":
        raise DirectPortError("truncation_policy_invalid")
    diagnostic = policy.get("diagnostic")
    if diagnostic != {"dropped_l2_over_total_l2": "finite_only", "zero_tail": "structural_enum", "acceptance_gate": "none"}:
        raise DirectPortError("truncation_diagnostic_invalid")
    true_keys = {"truncation_direct_port_implemented", "selected_truncation_policy_implemented"}
    gates = document.get("gates")
    if not isinstance(gates, dict) or set(gates) != true_keys | {"external_selected_truncation_invoked", "external_selected_truncation_admitted", "causal_impulse_admitted", "delay_extraction_implemented", "passivity_repair_implemented", "linear_convolution_implemented", "candidate_waveform_generated", "external_reference_binding_evaluated", "candidate_metric_acceptance_evaluated", "accepted_receiver", "product_runtime_invoked", "p4b_ami_runtime_invoked", "p5_reference_evaluated", "release_ledger_promoted"} or any(gates.get(key) is not True for key in true_keys) or any(gates.get(key) is not False for key in set(gates) - true_keys):
        raise DirectPortError("truncation_gate_promotion_invalid")
    blockers, claims = document.get("blockers"), document.get("non_claims")
    if not isinstance(blockers, list) or "external_selected_truncation_observation_missing" not in blockers or "linear_convolution_and_candidate_waveform_route_not_implemented" not in blockers or not isinstance(claims, list) or not any("not delay extraction" in item for item in claims if isinstance(item, str)):
        raise DirectPortError("truncation_nonclaim_or_blocker_relaxed")
    return {"valid": True, "truncation_implemented": True, "release_admitted": False}


def main() -> int:
    try:
        result = verify_document(yaml.safe_load(DEFAULT.read_text(encoding="utf-8")))
    except (OSError, ValueError, yaml.YAMLError, DirectPortError) as error:
        print(f"truncation_direct_port_failed:{error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
