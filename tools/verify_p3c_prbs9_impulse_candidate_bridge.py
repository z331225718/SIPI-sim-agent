"""Verify the fixed P3C PRBS9 discrete impulse-convolution bridge boundary."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-prbs9-impulse-candidate-bridge.v1.yaml"


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema") != "sipi.p3c-prbs9-impulse-candidate-bridge.v1" or document.get("status") != "fixed_prbs9_discrete_convolution_implemented_external_candidate_observation_pending":
            raise ValueError("schema_or_status")
        policy, gates = document.get("policy"), document.get("gates")
        if not isinstance(policy, dict) or policy.get("stimulus", {}).get("projection") != "ui_boundary_right_continuous_level_change" or policy["stimulus"].get("sub_strobe_100as_resolution") != "not_implemented" or policy["kernel"].get("expected_samples") != 10871 or policy["kernel"].get("tap_scaling") != "discrete_gain_no_dt_factor" or policy["convolution"] != {"implementation": "sipi_link::convolve_causal_fir_v1", "direct_full_linear": True, "fft": "prohibited", "circular_wrap": "prohibited", "zero_prehistory": True, "full_output_samples": 59926, "multiply_accumulates": 533287776, "strict_grid_prefix_samples": 49056, "metric_window": [32704, 49056], "alignment": "prohibited", "resampling": "prohibited"}:
            raise ValueError("policy")
        expected_true = {"fixed_prbs9_source_projection_implemented", "selected_discrete_linear_convolution_implemented"}
        expected_false = {"selected_truncated_response_admitted_as_discrete_convolution_kernel", "external_selected_candidate_convolution_invoked", "candidate_waveform_generated", "causal_impulse_admitted", "delay_extraction_implemented", "passivity_repair_implemented", "external_reference_binding_evaluated", "candidate_metric_acceptance_evaluated", "accepted_receiver", "product_runtime_invoked", "p4b_ami_runtime_invoked", "p5_reference_evaluated", "release_ledger_promoted"}
        if not isinstance(gates, dict) or set(gates) != expected_true | expected_false or any(gates[key] is not True for key in expected_true) or any(gates[key] is not False for key in expected_false):
            raise ValueError("gate_promotion")
        blockers = document.get("blockers")
        if not isinstance(blockers, list) or "external_selected_candidate_convolution_observation_missing" not in blockers or "bounded_response_not_admitted_as_physical_causal_impulse_or_fir" not in blockers:
            raise ValueError("blocker_relaxed")
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"p3c_prbs9_impulse_candidate_bridge_failed:{error}", file=sys.stderr)
        return 1
    print({"valid": True, "convolution_implemented": True, "release_admitted": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
