"""Verify the selected truncation waveform sensitivity core remains diagnostic-only."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/baselines/p3c-selected-truncation-waveform-sensitivity-core.v1.yaml"
MODULE = ROOT / "crates/sipi-p3c/src/p3c_truncation_waveform_sensitivity_v1.rs"


class VerificationError(ValueError):
    pass


def verify_document(document: object, source: str) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != "sipi.p3c-selected-truncation-waveform-sensitivity-core.v1":
        raise VerificationError("schema")
    if document.get("status") != "product_owned_selected_truncation_waveform_sensitivity_diagnostic_implemented_external_observation_pending":
        raise VerificationError("status")
    if document.get("profile") != {"input": "selected_bounded_causal_response_only", "kernel_samples": 51200, "output_window": [32704, 49056], "output_samples": 16352, "source": "fixed_prbs9_osr32_ui_boundary_right_continuous_zero_prehistory", "accumulation": "direct_kernel_index_ascending", "multiply_accumulates": 668477936, "sample_interval_bits": "3d712e0be826d695"}:
        raise VerificationError("profile")
    required_true = {"selected_truncation_waveform_sensitivity_diagnostic_defined"}
    required_false = {"external_full_causal_third_period_diagnostic_invoked", "current_truncated_baseline_reproduced", "truncation_waveform_sensitivity_observed", "bounded_causal_response_admitted_as_kernel", "causal_fir_admitted", "truncation_policy_changed", "candidate_waveform_generated", "selected_highloss_waveform_only_profile_accepted", "acceptance_ready", "promotion_eligible", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != required_true | required_false or any(admission[key] is not True for key in required_true) or any(admission[key] is not False for key in required_false):
        raise VerificationError("admission")
    for token in ("P3C_FULL_CAUSAL_RESPONSE_SAMPLES_V1: usize = 51_200", "P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_START_V1: usize = 32_704", "P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_SAMPLES_V1: usize = 16_352", "P3C_TRUNCATION_SENSITIVITY_MACS_V1: usize = 668_477_936", "kernel.iter().take(last_kernel + 1).enumerate()"):
        if token not in source:
            raise VerificationError("implementation_binding")
    if any(token in source for token in ("Fft", "CausalFirChannel", "convolve_causal_fir")):
        raise VerificationError("prohibited_implementation")
    return {"valid": True, "external_observed": False, "policy_changed": False, "release_admitted": False}


def main() -> int:
    try:
        result = verify_document(yaml.safe_load(BASELINE.read_text(encoding="utf-8")), MODULE.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_truncation_waveform_sensitivity_core_failed:{error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
