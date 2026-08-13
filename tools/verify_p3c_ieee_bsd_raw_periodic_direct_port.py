"""Verify the selected IEEE BSD raw-periodic direct-port boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-raw-periodic-direct-port.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ieee-com-sparam" / "src" / "s21_to_raw_periodic_v1.rs"
CARGO = ROOT / "crates" / "sipi-ieee-com-sparam" / "Cargo.toml"
NOTICE = ROOT / "crates" / "sipi-ieee-com-sparam" / "NOTICE-IEEE-802-COM.md"
SOURCE_MAP = ROOT / "crates" / "sipi-ieee-com-sparam" / "SOURCE-MAP.md"


class DirectPortError(RuntimeError):
    pass


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict):
        raise DirectPortError("manifest_not_mapping")
    if document.get("schema") != "sipi.p3c-ieee-bsd-raw-periodic-direct-port.v1":
        raise DirectPortError("schema_invalid")
    if document.get("status") != "selected_ieee_bsd3_raw_periodic_inverse_transform_implemented_causal_route_not_admitted":
        raise DirectPortError("status_invalid")
    source = document.get("source")
    if source != {
        "canonical_origin": "https://opensource.ieee.org/802-com/com_code.git",
        "commit": "d4ecd4597a98782887933b5df4c4796da2474195",
        "path": "src/s21_to_impulse_DC.m",
        "git_blob": "f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3",
        "content_sha256": "b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0",
        "license": "BSD-3-Clause",
        "excluded_source_objects": ["ieee-802-com-causality-delay-bsd3-v1"],
    }:
        raise DirectPortError("source_binding_invalid")
    expected_policy = {
        "input_type": "sipi_ieee_com_sparam::SelectedP3cUniformSpectrumV1",
        "one_sided_bin_requirement": "at_least_two",
        "transform_length": "two_times_one_sided_bin_count_minus_two",
        "hermitian_layout": "real_dc_positive_interior_real_nyquist_conjugate_negative_interior",
        "endpoint_imaginary_residual": {"absolute_limit": 1.0e-12, "relative_limit": 1.0e-10, "scale": "maximum_one_sided_complex_magnitude", "allowed_action": "bounded_projection_to_real"},
        "inverse": {"implementation": "rustfft_6_4_1_inverse", "exponent_sign": "positive", "normalization": "one_over_n", "imaginary_residual": {"absolute_limit": 1.0e-12, "relative_limit": 1.0e-10, "scale": "maximum_absolute_real_inverse_sample"}},
        "time_axis": {"sample_interval": "one_over_n_times_frequency_step", "indices": "half_open_zero_to_n_minus_one", "fftshift": "prohibited", "time_shift": "prohibited", "delay_removal": "prohibited", "alignment": "prohibited"},
        "truncation": "none_full_period_retained",
        "caller_overrides": "prohibited",
    }
    if document.get("policy") != expected_policy:
        raise DirectPortError("policy_invalid")
    gates = document.get("gates")
    true_keys = {"raw_periodic_inverse_transform_implemented", "s21_to_impulse_selected_transform_subset_implemented"}
    if not isinstance(gates, dict) or any(gates.get(key) is not True for key in true_keys) or any(gates.get(key) is not False for key in set(gates) - true_keys):
        raise DirectPortError("gate_relaxed")
    blockers = document.get("blockers")
    if not isinstance(blockers, list) or "external_selected_raw_periodic_response_observation_missing" not in blockers or "causality_delay_passivity_policy_not_implemented" not in blockers:
        raise DirectPortError("blocker_relaxed")
    return {"valid": True, "raw_periodic_implemented": True, "release_admitted": False}


def verify_files() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    cargo = CARGO.read_text(encoding="utf-8")
    notice = NOTICE.read_text(encoding="utf-8")
    source_map = SOURCE_MAP.read_text(encoding="utf-8")
    required = [
        ("rustfft = \"6.4.1\"", cargo),
        ("SPDX-License-Identifier: BSD-3-Clause", source),
        ("f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3", source),
        ("s21_to_impulse_DC.m", notice),
        ("s21_to_raw_periodic_v1.rs", source_map),
        ("calculate_delay_CausalityEnforcement.m", source_map),
    ]
    if any(token not in text for token, text in required):
        raise DirectPortError("license_notice_or_source_map_invalid")
    forbidden = ["Agent-COM", "PyBERT", "PyAMI", "fftshift", "CausalFir"]
    if any(token in source for token in forbidden):
        raise DirectPortError("unadmitted_transform_surface")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    try:
        report = verify_document(yaml.safe_load(args.manifest.read_text(encoding="utf-8")))
        verify_files()
    except (OSError, ValueError, yaml.YAMLError, DirectPortError) as error:
        report = {"status": "rejected", "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("status") != "rejected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
