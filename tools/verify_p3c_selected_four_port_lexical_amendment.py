"""Verify the narrow P3C four-port option-line lexical amendment."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-selected-four-port-lexical-amendment.v1.yaml"
PARSER = ROOT / "crates" / "sipi-touchstone" / "src" / "selected_four_port_v1.rs"
ADMISSION = ROOT / "crates" / "sipi-p3c" / "src" / "lib.rs"
SCHEMA = "sipi.p3c-selected-four-port-lexical-amendment.v1"


class VerificationError(ValueError):
    pass


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("lexical_amendment_schema_invalid")
    if document.get("status") != "product_lexical_v2_implemented_historical_v1_external_admission_rejected_pending_fresh_v2_custody":
        raise VerificationError("lexical_amendment_status_invalid")
    historical = document.get("historical_v1_rejected_observation")
    if historical != {
        "schema": "sipi.p3c.sealed-selected-s4p-custody-observation.v1", "status": "rejected",
        "reason": "clean_archive_runner_failed", "report_byte_length": 125,
        "report_content_sha256": "095d64e4ce2a5f5aaefaceb8055f2bd2667de5c4d5a0fb65714c8b4984292a13",
        "clean_archive_commit": "ac08d7830024cbc02630e26f5f508385b9ced77b",
        "selected_source": {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"},
        "observed_failure": "unsupported_option_line", "parser_profile": "selected_four_port_hz_s_ri_50_v1",
        "source_drift_preserved": True,
    }:
        raise VerificationError("lexical_amendment_history_invalid")
    if document.get("amendment") != {
        "v1_option_line_exact": "# Hz S RI R 50.0", "v2_option_lines_exact": ["# Hz S RI R 50", "# Hz S RI R 50.0"],
        "other_numeric_spellings": "reject", "generic_numeric_option_normalization": "prohibited",
        "option_token_case_or_whitespace_normalization": "prohibited",
        "data_format_parameter_unit_or_impedance_change": "prohibited",
    }:
        raise VerificationError("lexical_amendment_scope_invalid")
    expected_admission = {
        "lexical_v2_implemented": True, "sealed_s4p_v2_intake_implemented": True,
        "external_static_custody_observed": False, "selected_external_s4p_static_admitted": False,
        "real_constrained_fit_invoked": False, "analytic_stepping_implemented": False,
        "candidate_waveform_generated": False, "external_reference_binding_evaluated": False,
        "candidate_metric_acceptance_evaluated": False, "accepted_receiver": False,
        "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False,
        "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("lexical_amendment_promotion_invalid")
    if "two_fresh_external_sealed_s4p_v2_custody_observations_missing" not in set(document.get("blockers", [])):
        raise VerificationError("lexical_amendment_blocker_missing")
    parser = PARSER.read_text(encoding="utf-8")
    admission = ADMISSION.read_text(encoding="utf-8")
    required_parser = [
        "parse_selected_four_port_hz_s_ri_50_v1", "parse_selected_four_port_hz_s_ri_50_v2",
        "&[b\"# Hz S RI R 50.0\"]", "&[b\"# Hz S RI R 50\", b\"# Hz S RI R 50.0\"]",
    ]
    required_admission = ["SelectedP3cSealedS4pIdentityV2", "admit_selected_p3c_sealed_s4p_v1", "admit_selected_p3c_sealed_s4p_v2"]
    if any(token not in parser for token in required_parser) or any(token not in admission for token in required_admission):
        raise VerificationError("lexical_amendment_source_drift")
    forbidden_parser = ["parse::<f64>", "normalize_option"]
    if any(token in parser for token in forbidden_parser):
        raise VerificationError("lexical_amendment_normalization_surface")
    return {"valid": True, "lexical_v2_implemented": True, "external_static_custody_observed": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"selected_four_port_lexical_amendment_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
