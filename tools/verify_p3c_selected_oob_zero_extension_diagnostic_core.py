"""Verify the fixed selected `>40 GHz` zero-extension diagnostic core."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/baselines/p3c-selected-oob-zero-extension-diagnostic-core.v1.yaml"
SOURCE = ROOT / "crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs"


class VerificationError(ValueError):
    pass


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != "sipi.p3c-selected-oob-zero-extension-diagnostic-core.v1":
        raise VerificationError("oob_diagnostic_schema")
    if document.get("status") != "product_owned_selected_oob_zero_extension_diagnostic_implemented_external_observation_pending":
        raise VerificationError("oob_diagnostic_status")
    if document.get("authority") != {"actor": "user", "decision_ref": "user-continuation-2026-08-14", "scope": "selected_20mhz_512ghz_spectrum_sensitivity_only"}:
        raise VerificationError("oob_diagnostic_authority")
    profile = document.get("profile")
    if profile != {
        "input": "selected_uniform_spectrum_only",
        "input_bin_count": 25601,
        "frequency_step_hertz": 20000000.0,
        "preserve_inclusive_frequency_hertz": 40000000000.0,
        "first_zeroed_bin_index": 2001,
        "zeroed_bin_range": [2001, 25601],
        "replacement": "canonical_positive_complex_zero",
        "caller_configuration": "absent",
    }:
        raise VerificationError("oob_diagnostic_profile")
    required_prohibitions = {"cutoff_sweep", "taper", "window", "smoothing", "normalization", "interpolation_policy_change", "ads_grid_or_policy_import", "causality_bypass", "best_variant_selection", "candidate_acceptance"}
    if set(document.get("prohibitions", [])) != required_prohibitions:
        raise VerificationError("oob_diagnostic_prohibitions")
    if document.get("implementation") != {"crate": "sipi-ieee-com-sparam", "module": "interp_sparam_v1", "entrypoint": "zero_extend_selected_p3c_oob_diagnostic_v1", "public_cli": "absent", "external_asset_reads": "absent"}:
        raise VerificationError("oob_diagnostic_implementation")
    expected_admission = {
        "selected_oob_zero_extension_diagnostic_defined": True,
        "external_oob_extension_sensitivity_invoked": False,
        "baseline_current_candidate_reproduced": False,
        "oob_extension_sensitivity_observed": False,
        "product_interpolation_policy_changed": False,
        "selected_highloss_waveform_only_profile_accepted": False,
        "accepted_receiver": False,
        "acceptance_ready": False,
        "promotion_eligible": False,
        "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("oob_diagnostic_gate_relaxed")
    if any(token in str(document).lower() for token in ("file://", "http://", "https://", "samples: [", "waveform: [")):
        raise VerificationError("oob_diagnostic_evidence_leak")
    return {"valid": True, "external_observation": False, "product_policy_changed": False, "release_admitted": False}


def verify_source() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    required = (
        "SELECTED_OOB_ZERO_EXTENSION_BIN_COUNT_V1: usize = 25_601",
        "SELECTED_OOB_ZERO_EXTENSION_FIRST_ZERO_INDEX_V1: usize = 2_001",
        "SELECTED_OOB_ZERO_EXTENSION_FREQUENCY_STEP_HERTZ_V1: f64 = 20.0e6",
        "pub fn zero_extend_selected_p3c_oob_diagnostic_v1",
        "OobZeroExtensionDiagnosticErrorV1::SelectedGridMismatch",
        "Complex64::try_new(0.0, 0.0)",
    )
    if any(token not in source for token in required):
        raise VerificationError("oob_diagnostic_source_drift")
    prohibited = ("cutoff:", "taper", "window", "smoothing", "normaliz", "fftshift")
    function = source[source.index("pub fn zero_extend_selected_p3c_oob_diagnostic_v1"):source.index("fn magnitude")]
    if any(token in function.lower() for token in prohibited):
        raise VerificationError("oob_diagnostic_hidden_policy")


def main() -> int:
    try:
        document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_source()
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_oob_zero_extension_diagnostic_failed:{error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
