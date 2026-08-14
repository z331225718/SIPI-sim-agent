"""Verify the fixed selected-v3 residual diagnostic boundary."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/baselines/p3c-selected-highloss-residual-diagnostic-core.v1.yaml"
SOURCE = ROOT / "crates/sipi-compare/src/selected_highloss_prbs9_waveform_only_v3.rs"


def main() -> int:
    document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    expected = {
        "schema", "status", "authority", "predecessor", "profile", "prohibitions",
        "implementation", "admission", "blockers", "non_claims",
    }
    if not isinstance(document, dict) or set(document) != expected:
        print("selected_highloss_residual_diagnostic_core_failed:shape")
        return 1
    profile = document["profile"]
    admission = document["admission"]
    if (
        document["schema"] != "sipi.p3c-selected-highloss-residual-diagnostic-core.v1"
        or document["status"] != "product_owned_selected_highloss_strict_index_residual_diagnostic_implemented_external_observation_pending"
        or profile.get("fixed_period_windows") != [[0, 16352], [16352, 32704], [32704, 49056]]
        or profile.get("ui_partition") != {"third_period_uis": 511, "samples_per_ui": 32}
        or profile.get("third_period_nrmse_must_match_v3") is not True
        or admission.get("selected_waveform_residual_diagnostic_defined") is not True
        or any(admission.get(key) is not False for key in admission if key != "selected_waveform_residual_diagnostic_defined")
    ):
        print("selected_highloss_residual_diagnostic_core_failed:policy")
        return 1
    source = SOURCE.read_text(encoding="utf-8")
    required = [
        "pub fn diagnose_selected_highloss_prbs9_residual_v1",
        "sipi.compare.selected-highloss-prbs9-residual-period.v1",
        "sipi.compare.selected-highloss-prbs9-residual-ui-energy.v1",
        "third_period_maximum_energy_ui_offset",
    ]
    prohibited = ["fft", "correlation", "gain_fit", "dc_removal", "polarity_flip"]
    if any(token not in source for token in required) or any(token in source.lower() for token in prohibited):
        print("selected_highloss_residual_diagnostic_core_failed:implementation_boundary")
        return 1
    print({"valid": True, "external_observation": False, "acceptance_changed": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
