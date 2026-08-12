"""Fail-closed verifier for the P3C selected four-port static bench contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-selected-four-port-static-bench.v1.yaml"
SCHEMA = "sipi.p3c-selected-four-port-static-bench.v1"
SOURCE_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"


class VerificationError(ValueError):
    pass


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("static_bench_schema_invalid")
    if document.get("status") != "product_owned_static_parser_and_fixed_bench_reduction_specified_time_domain_executor_blocked":
        raise VerificationError("static_bench_status_invalid")
    selection = document.get("external_selection")
    if selection != {
        "logical_name": "channel_gen5_highloss.s4p",
        "byte_length": 1834156,
        "sha256": SOURCE_SHA256,
        "port_map": ["tx_plus", "rx_plus", "tx_minus", "rx_minus"],
        "asset_bytes_tracked": False,
    }:
        raise VerificationError("static_bench_source_binding_invalid")
    lexical = document.get("lexical_boundary")
    required_lexical = {
        "ports": 4,
        "option_line": "# Hz S RI R 50.0",
        "data_format": "ri",
        "parameter": "s",
        "reference_impedance_ohms": 50.0,
        "public_matrix_order": "incident_port_column_then_output_port_row",
        "continuation_lines": "data_tokens_only",
        "unsupported_keywords": "reject",
        "nonfinite_values": "reject",
        "nonincreasing_frequency": "reject",
    }
    if lexical != required_lexical:
        raise VerificationError("static_bench_lexical_boundary_invalid")
    if document.get("fixed_bench") != {
        "tx_sources": "complementary_ideal_prbssrc_each_internal_50_ohm",
        "rx_loads": "two_50_ohm_to_global_ground",
        "observation": "differential_rx_plus_minus_rx_minus",
        "reduction": "(S21-S23-S41+S43)/4",
        "caller_selectable_topology": False,
    }:
        raise VerificationError("static_bench_topology_invalid")
    implementation = document.get("implementation")
    if implementation != {
        "lexical_crate": "sipi-touchstone",
        "lexical_module": "selected_four_port_v1",
        "static_crate": "sipi-channel",
        "static_module": "p3c_fixed_four_port_bench_v1",
        "time_domain_executor": "not_implemented",
    }:
        raise VerificationError("static_bench_implementation_invalid")
    admission = document.get("admission")
    expected_admission = {
        "external_static_admission_evaluated": False,
        "candidate_waveform_generated": False,
        "external_reference_binding": "not_evaluated",
        "accepted_receiver": False,
        "acceptance_ready": False,
        "promotion_eligible": False,
        "product_runtime_invoked": False,
        "p4b_ami_runtime_invoked": False,
        "release_ledger_promoted": False,
    }
    if (
        not isinstance(admission, dict)
        or admission != expected_admission
    ):
        raise VerificationError("static_bench_admission_promoted")
    blockers = document.get("blockers")
    if not isinstance(blockers, list) or "time_domain_network_policy_missing" not in blockers:
        raise VerificationError("static_bench_time_domain_gate_missing")
    if not isinstance(document.get("non_claims"), list) or len(document["non_claims"]) < 3:
        raise VerificationError("static_bench_nonclaims_invalid")
    return {"valid": True, "content_sha256": content_sha256(DEFAULT)}


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        print(verify(document))
    except (OSError, VerificationError, yaml.YAMLError) as error:
        print(f"static_bench_verification_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
