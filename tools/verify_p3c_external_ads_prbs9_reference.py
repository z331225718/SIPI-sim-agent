"""Verify the v2-contract external ADS oracle reference without promotion."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-external-ads-prbs9-reference.v1.yaml"
V1 = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v1.yaml"
V2 = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v2.yaml"
ATTEMPT = ROOT / "docs/baselines/p3c-external-ads-prbs9-reference-attempt.v1.yaml"
P4B = ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-external-ads-prbs9-reference.v1"
V1_SHA256 = "7c55086abe681e4a4a64aec15379eb839fc3514a94b2f4b3d920ec9c9f391751"
V2_SHA256 = "f47329b6ddda01cbcde1f24e21cb93e03f8ef6139ea2d43ff74cad9e2049d2b5"
ATTEMPT_SHA256 = "083b20ad6d7c386370230fb5819c168146f484024de6b0d553a1577c052df3e7"
ARCHIVE_COMMIT = "e167c579ec85c1d8c49301f8eaefa832bc9f5c3a"
ARCHIVE_TREE = "d8c8b7ab35257209377170e782a038ba5145fb56"
ARCHIVE_RUNNER_SHA256 = "5c67ffeae954c34dbcf31096093d1a3f44a2eaeeb15ca3bb009b7139fe78c663"
REPORT_SHA256 = "bc542f13dae25d0261dc001f814fc1b721cdf534455589448cdaa4f6ae05b695"
MANIFEST_SHA256 = "37930afa7f151cd6ca317f17ebb544dfb9c5a56a4a4c455b35f0114dc4fb94f9"
SOURCE_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"
PAYLOAD_SHA256 = "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726"
THIRD_SHA256 = "402596d9f5ab37e37cc3f4927f55170ab007159376174453fc65b78e3a80d31c"


class ReferenceError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReferenceError("document_not_mapping")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_hashes(root: Path) -> set[str]:
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True)
    return {hashlib.sha256((root / item.decode("utf-8")).read_bytes()).hexdigest() for item in result.stdout.split(b"\0") if item}


def archive_runner_bytes(root: Path) -> bytes:
    member = "tools/run_p3c_external_ads_prbs9_reference.py"
    archive = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", ARCHIVE_COMMIT, member], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        entry = bundle.extractfile(member)
        if entry is None:
            raise ReferenceError("clean_archive_runner_missing")
        return entry.read()


def verify_clean_archive(root: Path) -> None:
    tree = subprocess.run(["git", "-C", str(root), "rev-parse", f"{ARCHIVE_COMMIT}^{{tree}}"], check=True, capture_output=True, text=True).stdout.strip()
    if tree != ARCHIVE_TREE:
        raise ReferenceError("clean_archive_tree_drift")
    runner = archive_runner_bytes(root)
    if hashlib.sha256(runner).hexdigest() != ARCHIVE_RUNNER_SHA256:
        raise ReferenceError("clean_archive_runner_drift")


def verify_gates(root: Path) -> None:
    if sha256_file(root / V1.relative_to(ROOT)) != V1_SHA256 or sha256_file(root / V2.relative_to(ROOT)) != V2_SHA256:
        raise ReferenceError("contract_source_drift")
    v2 = load_yaml(root / V2.relative_to(ROOT))
    if v2.get("status") != "specified_external_ads_100as_reference_and_accepted_receiver_pending" or v2.get("stimulus", {}).get("transition", {}).get("rise_time_seconds") != 1.0e-16 or v2.get("admission", {}).get("external_reference_observed") is not False:
        raise ReferenceError("contract_v2_gate_drift")
    if sha256_file(root / ATTEMPT.relative_to(ROOT)) != ATTEMPT_SHA256:
        raise ReferenceError("historical_attempt_source_drift")
    attempt = load_yaml(root / ATTEMPT.relative_to(ROOT))
    if attempt.get("status") != "external_ads_runtime_observed_reference_contract_rejected" or attempt.get("contract_result", {}).get("reference_contract_match") is not False or attempt.get("admission", {}).get("external_reference_observed") is not False:
        raise ReferenceError("historical_attempt_promotion_drift")
    p4b = load_yaml(root / P4B.relative_to(ROOT))
    if p4b.get("status") != "external_only_identity_observed_worker_blocked":
        raise ReferenceError("p4b_runtime_admission_drift")
    publication = json.loads((root / PUBLICATION.relative_to(ROOT)).read_text(encoding="utf-8"))
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or compare.get("acceptance_state") != "specified" or "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise ReferenceError("release_compare_metric_gate_drift")


def verify_document(document: object, *, root: Path = ROOT, hashes: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "external_ads_reference_observed_contract_v2_matched_candidate_and_receiver_acceptance_pending":
        raise ReferenceError("schema_or_status_invalid")
    if document.get("authority") != {"actor": "user", "decision_ref": "user-authorized-2026-08-12-p3c-ads-prbssrc-100as-source-edge", "scope": "external_ads_oracle_reference_only_not_product_or_p4b_runtime"}:
        raise ReferenceError("authority_invalid")
    if document.get("contract_binding") != {"contract_v1_content_sha256": V1_SHA256, "contract_v2_content_sha256": V2_SHA256, "historical_attempt_content_sha256": ATTEMPT_SHA256}:
        raise ReferenceError("contract_binding_invalid")
    if document.get("external_observation") != {"schema": "sipi.p3c-external-ads-prbs9-reference-observation.v2", "custody": "external_only", "report_path_retained": False, "report_byte_length": 2639, "report_content_sha256": REPORT_SHA256}:
        raise ReferenceError("external_observation_invalid")
    if document.get("clean_archive") != {"commit": ARCHIVE_COMMIT, "tree": ARCHIVE_TREE, "runner_sha256": ARCHIVE_RUNNER_SHA256}:
        raise ReferenceError("clean_archive_binding_invalid")
    if document.get("ads") != {"product": "ads_2026_update1", "python_version": "3.13.2", "simulator_build": "hpeesofsim_635_shp_2025-10-26"}:
        raise ReferenceError("ads_identity_invalid")
    if document.get("source") != {"logical_name": "channel_gen5_highloss.s4p", "byte_length": 1834156, "sha256": SOURCE_SHA256, "port_map": {"port_1": "tx_plus", "port_2": "rx_plus", "port_3": "tx_minus", "port_4": "rx_minus"}}:
        raise ReferenceError("source_identity_invalid")
    if document.get("source_edge") != {"component_semantics": "ads_prbssrc", "edge_shape_code": 0, "rise_time_seconds": 1.0e-16, "fall_time_seconds": 1.0e-16, "transition_reference": 0.0, "clamp_warning_observed": False}:
        raise ReferenceError("source_edge_invalid")
    if document.get("fresh_runs") != {"count": 2, "manifest_byte_length": 2479, "manifest_sha256": MANIFEST_SHA256, "netlist_sha256": "2784e9e8d42c7ecdc3459b79a5f9cd79cc86131f839c86b1658e8d40b1d9aaf9", "canonical_payload_repeatability": "identical"}:
        raise ReferenceError("fresh_run_binding_invalid")
    if document.get("output") != {"observation_node": "V(rxp)-V(rxm)", "unit": "volts_differential", "ads_samples_inclusive": 49057, "contract_half_open_samples": 49056, "third_period_samples": 16352, "canonical_payload_sha256": PAYLOAD_SHA256, "third_period_payload_sha256": THIRD_SHA256, "historical_waveform_identity_match": True}:
        raise ReferenceError("output_identity_invalid")
    expected_admission = {"external_ads_runtime_observed": True, "reference_contract_match": True, "external_reference_observed": True, "candidate_waveform_eye_jitter_acceptance_evaluated": False, "accepted_receiver": False, "acceptance_ready": False, "promotion_eligible": False, "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False, "release_ledger_promoted": False}
    if document.get("admission") != expected_admission:
        raise ReferenceError("admission_gate_drift")
    if document.get("blockers") != ["candidate_waveform_eye_jitter_comparator_missing", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing"]:
        raise ReferenceError("blockers_invalid")
    if document.get("non_claims") != ["Not a product waveform, eye, jitter, receiver, or release acceptance result.", "Not product runtime, AMI, IBIS, DLL, CDR, equalizer, or statistical-eye execution.", "Not authorization to promote P4B, release compare, or release ledger evidence."]:
        raise ReferenceError("non_claims_invalid")
    actual_hashes = tracked_hashes(root) if hashes is None else hashes
    if {REPORT_SHA256, MANIFEST_SHA256, SOURCE_SHA256, PAYLOAD_SHA256, THIRD_SHA256} & actual_hashes:
        raise ReferenceError("external_custody_leak")
    verify_clean_archive(root)
    verify_gates(root)
    return {"schema": SCHEMA, "status": document["status"], "external_ads_runtime_observed": True, "external_reference_observed": True, "candidate_acceptance_evaluated": False, "release_promoted": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        report = verify_document(load_yaml(arguments.reference))
    except (OSError, ValueError, yaml.YAMLError, subprocess.CalledProcessError, ReferenceError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
