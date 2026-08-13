"""Verify the hash-only external selected-S4P impulse causality diagnostic evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p3c.selected-s4p-impulse-causality-diagnostic-evidence.v1"
DEFAULT = ROOT / "docs" / "baselines" / "p3c-selected-s4p-impulse-causality-diagnostic-evidence.v1.yaml"


class EvidenceError(RuntimeError):
    pass


def expected() -> dict:
    return {
        "schema": SCHEMA,
        "status": "external_exact_grid_impulse_diagnostic_observed_raw_impulse_not_admitted_thresholds_were_unset",
        "contract": {"path": "docs/baselines/p3c-selected-s4p-impulse-causality-diagnostic-contract.v1.yaml", "schema": "sipi.p3c-selected-s4p-impulse-causality-diagnostic-contract.v1", "status": "external_only_diagnostic_authorized_pending_owner_thresholds"},
        "external_observation": {
            "schema": "sipi.p3c.sealed-selected-s4p-impulse-causality-diagnostic-observation.v1", "status": "observed", "custody": "external_only", "report_path_retained": False,
            "report_sha256": "6cccc07a9505e46139dd4a4e6f4ae02dbe86ac7b39e08445e1186bae3c4956de",
            "selected_source": {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"},
            "clean_archive_commit": "bc331c889213d7f287c4f5d833b129af5e95dfa6", "fresh_custody_runs": 2,
            "product_source_inventory": {"Cargo.lock": "d1248e7537ad15263b84b41f172ed73090faf6da7e5fbf3c7afac60e1e3e4583", "crates/sipi-artifacts/src/lib.rs": "85b475ec865779dbe3e21b54759ca9075b8a4516714d7192ba4b214075861997", "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs": "248bf24c494d9c956a96e2781f35f546d5de9f70f6157457da7a54aeb60baa70", "crates/sipi-p3c/Cargo.toml": "ef5e9a8951ffccbbd83472dbda8b4fad0a5ca3714bb7975755c0f85d59c0d8d8", "crates/sipi-p3c/src/lib.rs": "aaf4b40fcc17d4ff2ae4ab512ecf7d68416dea6aaa8c4254521ae1ab57813b36", "crates/sipi-p3c/tests/p3c_sealed_s4p_external_impulse_diagnostic_runner.rs": "04fe5a98b22651328c5fd4ff9233a2a5100e65f7148a88aa5320dec6aae7016d", "crates/sipi-touchstone/src/selected_four_port_v1.rs": "53b11a0cf08b0505c190b244c47f13e22f7b2b3c1f6ea712b6aba533a8805f80"},
            "runner_source_sha256": "04fe5a98b22651328c5fd4ff9233a2a5100e65f7148a88aa5320dec6aae7016d",
            "manifest_sha256s": ["442c5c89eff11e2f6719b9a92d492f92febb91fb61f8e8286ed69d6b63591253", "d3109d7025d5783cb9639a3229468086edeac1e8f9d92433951fe6b390612756"],
            "record_count": 2002, "impulse_sha256": "3656a4b519ed967047409a0d6dec0124c33393e40e932a7142f0dc27ab75b0e7",
            "negative_energy_fraction_bits": "3fdfffff6e309ab3", "negative_peak_fraction_bits": "3feff89c207d6596", "signed_peak_index": 3429,
            "source_identity_checks": "before_stage_after_equal", "cleanup_status": "complete",
        },
        "observed_interpretation": {"exact_grid_impulse_diagnostic_observed": True, "finite_band_raw_quadrature_negative_time_content_observed": True, "threshold_selected": False, "causal_impulse_admitted": False, "sampled_four_port_passivity_admitted": False, "causal_repair_or_delay_shift_applied": False, "product_impulse_execution_implemented": False},
        "blockers": ["product_finite_band_causality_policy_not_selected", "product_passivity_policy_not_selected", "direct_port_sparameter_policy_not_selected", "direct_port_implementation_scope_missing", "p5_authoritative_r480_reference_missing"],
        "non_claims": [
            "The observed negative-time metrics describe only the disclosed finite-band exact-grid quadrature, not the physical channel's continuous-time causality or a threshold pass/fail result.",
            "No interpolation, extrapolation, window, taper, delay extraction, causal repair, passivity repair, PRBS source, convolution, waveform, receiver, or ADS-equivalence result is claimed.",
            "This evidence does not admit the IEEE BSD source inputs into a Rust implementation or select their algorithmic options.",
            "Candidate acceptance, external reference binding, P4B/AMI runtime, P5 reference, release acceptance, and historical source-drift gates remain unchanged.",
        ],
    }


def verify_document(document: object) -> dict:
    if document != expected():
        raise EvidenceError("diagnostic_evidence_identity_or_gate_mismatch")
    return {"schema": SCHEMA, "status": expected()["status"], "fresh_custody_runs": 2, "causal_impulse_admitted": False, "release_admitted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT)
    args = parser.parse_args()
    try:
        result = verify_document(yaml.safe_load(args.evidence.read_text(encoding="utf-8")))
    except (OSError, ValueError, yaml.YAMLError, EvidenceError) as error:
        result = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] != "rejected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
