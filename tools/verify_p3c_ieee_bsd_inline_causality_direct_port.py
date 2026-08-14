"""Verify the selected IEEE BSD bounded inline-causality direct port."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-inline-causality-direct-port.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ieee-com-sparam" / "src" / "s21_to_causal_v1.rs"
SOURCE_MAP = ROOT / "crates" / "sipi-ieee-com-sparam" / "SOURCE-MAP.md"
NOTICE = ROOT / "crates" / "sipi-ieee-com-sparam" / "NOTICE-IEEE-802-COM.md"


class DirectPortError(RuntimeError):
    pass


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != "sipi.p3c-ieee-bsd-inline-causality-direct-port.v1":
        raise DirectPortError("causality_direct_port_schema_invalid")
    if document.get("status") != "selected_ieee_bsd3_bounded_inline_causality_implemented_external_admission_pending":
        raise DirectPortError("causality_direct_port_status_invalid")
    if document.get("source") != {
        "canonical_origin": "https://opensource.ieee.org/802-com/com_code.git",
        "commit": "d4ecd4597a98782887933b5df4c4796da2474195",
        "path": "src/s21_to_impulse_DC.m",
        "git_blob": "f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3",
        "content_sha256": "b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0",
        "license": "BSD-3-Clause",
        "included_upstream_lines": [66, 88, 92, 94],
        "excluded_source_objects": ["ieee-802-com-causality-delay-bsd3-v1"],
    }:
        raise DirectPortError("causality_direct_port_source_binding_invalid")
    policy = document.get("policy")
    if not isinstance(policy, dict) or policy.get("enforce_causality") is not True or policy.get("pulse_tolerance") != 0.05 or policy.get("relative_tolerance") != 0.006 or policy.get("successive_difference_tolerance") != 1.0e-4 or policy.get("maximum_iterations") != 256 or policy.get("caller_overrides") != "prohibited":
        raise DirectPortError("causality_direct_port_policy_invalid")
    if policy.get("zero_windows") != {"prefix": "zero_based_inclusive_zero_through_start", "suffix": "zero_based_half_open_floor_length_divided_by_two_minus_one_to_length"} or policy.get("error", {}).get("reject_when") != "nonpositive_or_nonfinite" or policy.get("stop", {}).get("output") != "source_pre_projection_zero_window_response":
        raise DirectPortError("causality_direct_port_semantics_relaxed")
    gates = document.get("gates")
    true_keys = {"inline_causality_direct_port_implemented", "bounded_causality_policy_implemented"}
    if not isinstance(gates, dict) or any(gates.get(key) is not True for key in true_keys) or any(gates.get(key) is not False for key in set(gates) - true_keys):
        raise DirectPortError("causality_direct_port_gate_relaxed")
    blockers = document.get("blockers")
    if not isinstance(blockers, list) or "external_selected_causality_observation_missing" not in blockers or "named_author_helper_remains_blocked_for_delay_path" not in blockers:
        raise DirectPortError("causality_direct_port_blocker_relaxed")
    return {"valid": True, "causality_implemented": True, "release_admitted": False}


def verify_files() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    source_map = SOURCE_MAP.read_text(encoding="utf-8")
    notice = NOTICE.read_text(encoding="utf-8")
    required = [
        "SPDX-License-Identifier: BSD-3-Clause",
        "f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3",
        "SELECTED_CAUSALITY_MAX_ITERATIONS_V1: usize = 256",
        "InputAllZero",
        "IterationLimitExceeded",
    ]
    if any(token not in source for token in required):
        raise DirectPortError("causality_direct_port_source_map_invalid")
    if "s21_to_causal_v1.rs" not in source_map or "calculate_delay_CausalityEnforcement.m" not in source_map or "s21_to_impulse_DC.m" not in notice:
        raise DirectPortError("causality_direct_port_notice_invalid")
    forbidden = ["Agent-COM", "PyBERT", "PyAMI", "CausalFir", "truncation_threshold", "calculate_delay_CausalityEnforcement("]
    if any(token in source for token in forbidden):
        raise DirectPortError("causality_direct_port_unadmitted_surface")


def main() -> int:
    try:
        report = verify_document(yaml.safe_load(MANIFEST.read_text(encoding="utf-8")))
        verify_files()
    except (OSError, ValueError, yaml.YAMLError, DirectPortError) as error:
        report = {"status": "rejected", "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("status") != "rejected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
