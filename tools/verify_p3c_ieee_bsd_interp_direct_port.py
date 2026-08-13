"""Verify the selected IEEE BSD interpolation direct-port boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-interp-direct-port.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ieee-com-sparam" / "src" / "interp_sparam_v1.rs"
CARGO = ROOT / "crates" / "sipi-ieee-com-sparam" / "Cargo.toml"
NOTICE = ROOT / "crates" / "sipi-ieee-com-sparam" / "NOTICE-IEEE-802-COM.md"
SOURCE_MAP = ROOT / "crates" / "sipi-ieee-com-sparam" / "SOURCE-MAP.md"


class DirectPortError(RuntimeError):
    pass


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict):
        raise DirectPortError("manifest_not_mapping")
    expected = {
        "schema": "sipi.p3c-ieee-bsd-interp-direct-port.v1",
        "status": "selected_ieee_bsd3_interpolation_leaf_implemented_impulse_route_not_admitted",
        "source": {
            "canonical_origin": "https://opensource.ieee.org/802-com/com_code.git",
            "commit": "d4ecd4597a98782887933b5df4c4796da2474195",
            "path": "src/interp_Sparam.m",
            "git_blob": "85b52ff25dbb5bb91f032a03d7cdd311e33af432",
            "content_sha256": "259762276a3711eb6e9186993ae1cf38b9cb60d4819f263dc7770788a7f90e27",
            "license": "BSD-3-Clause",
            "excluded_source_objects": ["ieee-802-com-s21-to-impulse-dc-bsd3-v1", "ieee-802-com-causality-delay-bsd3-v1"],
        },
        "policy": {
            "sample_interval_seconds": 9.765625e-13,
            "nyquist_hertz": 512000000000.0,
            "output_grid": "source_df_then_positive_matlab_round_to_nyquist",
            "max_output_bins": 1048576,
            "magnitude_branch": "linear_trend_to_DC_log_trend_to_inf",
            "phase_branch": "trend_and_shift_to_DC",
            "phase_unwrap": "enabled",
            "anti_causal_mean_phase_slope": "reject",
            "debug_bypass": "prohibited",
            "caller_overrides": "prohibited",
        },
    }
    for key, value in expected.items():
        actual = document.get(key)
        if isinstance(value, dict):
            if not isinstance(actual, dict) or any(actual.get(subkey) != subvalue for subkey, subvalue in value.items()):
                raise DirectPortError(f"{key}_identity_or_policy_mismatch")
        elif actual != value:
            raise DirectPortError(f"{key}_mismatch")
    gates = document.get("gates")
    if not isinstance(gates, dict) or gates.get("selected_interpolation_core_implemented") is not None:
        raise DirectPortError("unexpected_gate_promotion")
    required_false = [key for key in gates if key != "uniform_spectrum_is_not_causalized"]
    if gates.get("uniform_spectrum_is_not_causalized") is not True or any(gates.get(key) is not False for key in required_false):
        raise DirectPortError("gate_relaxed")
    return {"schema": document["schema"], "status": document["status"], "release_admitted": False}


def verify_files() -> None:
    cargo = CARGO.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
    notice = NOTICE.read_text(encoding="utf-8")
    source_map = SOURCE_MAP.read_text(encoding="utf-8")
    required = [
        ('license = "BSD-3-Clause"', cargo),
        ("publish = false", cargo),
        ("SPDX-License-Identifier: BSD-3-Clause", source),
        ("85b52ff25dbb5bb91f032a03d7cdd311e33af432", source),
        ("Copyright 2025 802-COM Authors", notice),
        ("s21_to_impulse_DC.m", source_map),
        ("calculate_delay_CausalityEnforcement.m", source_map),
    ]
    if any(token not in text for token, text in required):
        raise DirectPortError("license_notice_or_source_map_mismatch")
    forbidden = ["Agent-COM", "PyBERT", "PyAMI"]
    if any(token in source for token in forbidden):
        raise DirectPortError("unadmitted_source_reference_in_translation")


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
