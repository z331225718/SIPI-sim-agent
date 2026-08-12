"""Fail closed on the external ADS PRBS9 trial's rejected contract result."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-external-ads-prbs9-reference-attempt.v1.yaml"
CONTRACT = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v1.yaml"
P4B = ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-external-ads-prbs9-reference-attempt.v1"
HEX64 = set("0123456789abcdef")
EXPECTED = {
    "source": (1834156, "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"),
    "period": "4437fb3beb2fa1ca99b4177673c53fc20089ac9cf68b1adaa1e0fad14d742127",
    "net_payload": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726",
    "third_payload": "402596d9f5ab37e37cc3f4927f55170ab007159376174453fc65b78e3a80d31c",
    "report": (2429, "eed37c9434b78ef6bd05ef754bd2a5bb6dfc4cb0508d873f8a897a2a58502f9a"),
}


class AttemptError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AttemptError("document_not_mapping")
    return value


def is_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def tracked_hashes(root: Path) -> set[str]:
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True)
    return {hashlib.sha256((root / item.decode("utf-8")).read_bytes()).hexdigest() for item in result.stdout.split(b"\0") if item}


def verify_gates(root: Path) -> None:
    contract = load_yaml(root / CONTRACT.relative_to(ROOT))
    if contract.get("status") != "specified_external_reference_and_accepted_receiver_pending" or contract["reference"].get("external_observed") is not False or contract["admission"].get("ads_runtime_invoked") is not False:
        raise AttemptError("p3c_contract_promotion_drift")
    p4b = load_yaml(root / P4B.relative_to(ROOT))
    if p4b.get("status") != "external_only_identity_observed_worker_blocked":
        raise AttemptError("p4b_runtime_admission_drift")
    publication = json.loads((root / PUBLICATION.relative_to(ROOT)).read_text(encoding="utf-8"))
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or compare.get("acceptance_state") != "specified" or "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise AttemptError("release_compare_metric_gate_drift")


def verify_document(document: object, *, root: Path = ROOT, hashes: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "external_ads_runtime_observed_reference_contract_rejected":
        raise AttemptError("schema_or_status_invalid")
    if document.get("authority") != {"actor": "user", "decision_ref": "user-authorized-2026-08-12-local-ads-python-reference-lane", "scope": "external_ads_ideal_load_only_not_p4b_or_product_runtime"}:
        raise AttemptError("authority_invalid")
    observation = document.get("external_observation")
    expected_observation = {"schema": "sipi.p3c-external-ads-prbs9-reference-observation.v1", "custody": "external_only", "report_path_retained": False, "report_byte_length": EXPECTED["report"][0], "report_content_sha256": EXPECTED["report"][1], "ads": {"product": "ads_2026_update1", "python_version": "3.13.2", "simulator_build": "hpeesofsim_635_shp_2025-10-26"}, "fresh_run_count": 2, "canonical_payload_repeatability": "identical"}
    if observation != expected_observation:
        raise AttemptError("external_observation_invalid")
    source = document.get("source")
    if source != {"logical_name": "channel_gen5_highloss.s4p", "byte_length": EXPECTED["source"][0], "sha256": EXPECTED["source"][1], "port_map": {"port_1": "tx_plus", "port_2": "rx_plus", "port_3": "tx_minus", "port_4": "rx_minus"}}:
        raise AttemptError("source_identity_or_port_map_invalid")
    if document.get("stimulus") != {"prbs_period_sha256": EXPECTED["period"], "seed_hex": 0x1A5, "periods": 3, "symbol_rate_gbaud": 32.0, "samples_per_ui": 32}:
        raise AttemptError("stimulus_invalid")
    if document.get("topology") != {"tx": "two_complementary_ideal_prbssrc_sources_with_internal_50_ohm_rout", "channel": "four_port_touchstone", "rx": "two_50_ohm_to_global_ground_loads", "observation": "V(rxp)-V(rxm)"}:
        raise AttemptError("topology_invalid")
    expected_output = {"ads_samples_inclusive": 49057, "contract_half_open_samples": 49056, "sample_interval_seconds": 9.765625e-13, "canonical_payload_format": "little_endian_f64_time_tx_differential_rx_differential", "canonical_payload_sha256": EXPECTED["net_payload"], "third_period_payload_sha256": EXPECTED["third_payload"]}
    if document.get("output") != expected_output:
        raise AttemptError("output_identity_invalid")
    if document.get("contract_result") != {"reference_contract_match": False, "mismatch_reason": "ads_prbssrc_clamps_requested_zero_rise_and_fall_to_100_asec", "source_edge_floor_seconds": 1.0e-16}:
        raise AttemptError("contract_rejection_invalid")
    if document.get("admission") != {"acceptance_ready": False, "promotion_eligible": False, "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False, "external_reference_observed": False, "release_ledger_promoted": False}:
        raise AttemptError("admission_gate_drift")
    if document.get("blockers") != ["ads_rectangular_nrz_source_edge_floor_owner_disposition_missing", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing"]:
        raise AttemptError("blockers_invalid")
    if document.get("non_claims") != ["Not a P3C waveform, eye, jitter, receiver, or release acceptance result.", "Not product runtime, AMI, IBIS, DLL, CDR, equalizer, or statistical-eye execution.", "Not authorization to alter the rectangular-NRZ contract or suppress the ADS source-edge floor."]:
        raise AttemptError("non_claims_invalid")
    if not all(is_hash(value) for value in (source["sha256"], observation["report_content_sha256"], expected_output["canonical_payload_sha256"], expected_output["third_period_payload_sha256"])):
        raise AttemptError("hash_invalid")
    actual_hashes = tracked_hashes(root) if hashes is None else hashes
    if {source["sha256"], observation["report_content_sha256"], expected_output["canonical_payload_sha256"], expected_output["third_period_payload_sha256"]} & actual_hashes:
        raise AttemptError("external_custody_leak")
    verify_gates(root)
    return {"schema": SCHEMA, "status": document["status"], "reference_contract_match": False, "ads_runtime_observed": True, "external_reference_observed": False, "release_promoted": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.attempt))
    except (OSError, ValueError, yaml.YAMLError, subprocess.CalledProcessError, AttemptError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
