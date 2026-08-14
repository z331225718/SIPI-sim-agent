"""Verify the narrow IEEE BSD inline-causality source observation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-inline-causality-source-preflight.v1.yaml"
SOURCE_MAP = ROOT / "crates" / "sipi-ieee-com-sparam" / "SOURCE-MAP.md"
NOTICE = ROOT / "crates" / "sipi-ieee-com-sparam" / "NOTICE-IEEE-802-COM.md"


class PreflightError(RuntimeError):
    pass


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != "sipi.p3c-ieee-bsd-inline-causality-source-preflight.v1":
        raise PreflightError("inline_causality_schema_invalid")
    if document.get("status") != "ieee_bsd_inline_causality_loop_observed_policy_and_implementation_pending":
        raise PreflightError("inline_causality_status_invalid")
    source = document.get("source")
    if source != {
        "canonical_origin": "https://opensource.ieee.org/802-com/com_code.git",
        "commit": "d4ecd4597a98782887933b5df4c4796da2474195",
        "path": "src/s21_to_impulse_DC.m",
        "git_blob": "f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3",
        "byte_length": 4208,
        "content_sha256": "b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0",
        "license": "BSD-3-Clause",
        "eligible_material": "ieee-802-com-s21-to-impulse-dc-bsd3-v1",
    }:
        raise PreflightError("inline_causality_source_binding_invalid")
    loop = document.get("inline_causality_loop")
    expected_loop = {
        "upstream_lines": [66, 94],
        "method_marker": "Alternating Projections Method",
        "required_inputs": ["EC_PULSE_TOL", "EC_REL_TOL", "EC_DIFF_TOL", "ENFORCE_CAUSALITY"],
        "observed_operations": ["first_half_abs_peak_threshold", "zero_prefix_through_start_index", "zero_second_half_from_floor_half_index", "fixed_magnitude_phase_projection", "fft_ifft_iteration", "relative_or_successive_difference_stop"],
        "direct_calls": ["interp_Sparam", "fft", "ifft"],
        "excluded_from_this_loop": ["calculate_delay_CausalityEnforcement", "impulse_response_truncation_threshold", "delay_extraction", "passivity_repair"],
    }
    if loop != expected_loop:
        raise PreflightError("inline_causality_loop_scope_invalid")
    if document.get("dependency_boundary") != {
        "allowed_existing_materials": ["ieee-802-com-s21-to-impulse-dc-bsd3-v1", "ieee-802-com-interp-sparam-bsd3-v1"],
        "blocked_materials": ["ieee-802-com-causality-delay-bsd3-v1"],
        "conclusion": "named_author_helper_is_not_a_direct_dependency_of_the_observed_inline_loop",
    }:
        raise PreflightError("inline_causality_dependency_boundary_invalid")
    gates = document.get("gates")
    true_keys = {"inline_causality_source_observed", "inline_causality_dependency_closure_observed"}
    if not isinstance(gates, dict) or any(gates.get(key) is not True for key in true_keys) or any(gates.get(key) is not False for key in set(gates) - true_keys):
        raise PreflightError("inline_causality_gate_relaxed")
    blockers = document.get("blockers")
    if not isinstance(blockers, list) or "inline_causality_policy_values_and_failure_semantics_not_owner_confirmed" not in blockers or "named_author_helper_remains_blocked_for_delay_path" not in blockers:
        raise PreflightError("inline_causality_blocker_relaxed")
    claims = document.get("non_claims")
    if not isinstance(claims, list) or not any("named-author helper remains blocked" in item for item in claims if isinstance(item, str)):
        raise PreflightError("inline_causality_nonclaim_missing")
    return {"valid": True, "inline_causality_source_observed": True, "release_admitted": False}


def verify_files() -> None:
    source_map = SOURCE_MAP.read_text(encoding="utf-8")
    notice = NOTICE.read_text(encoding="utf-8")
    required = [
        "s21_to_impulse_DC.m",
        "f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3",
        "calculate_delay_CausalityEnforcement.m",
    ]
    if any(token not in source_map for token in required) or "s21_to_impulse_DC.m" not in notice:
        raise PreflightError("inline_causality_license_or_source_map_invalid")


def main() -> int:
    try:
        report = verify_document(yaml.safe_load(MANIFEST.read_text(encoding="utf-8")))
        verify_files()
    except (OSError, ValueError, yaml.YAMLError, PreflightError) as error:
        report = {"status": "rejected", "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("status") != "rejected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
