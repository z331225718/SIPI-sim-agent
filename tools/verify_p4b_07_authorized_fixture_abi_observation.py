"""Fail closed on the P4B-07a authorized-fixture ABI observation.

The charter fixes the probe surface; the evidence records the two-fresh-
custody hash-only observation (TX probes succeed, RX AMI_Init crashes
reproducibly on the fixed surface). The verifier binds charter, evidence,
material registry hashes, and the PLAN P4B-07a row; any drift fails
closed. No claim about DLL internals, parity, or compatibility is made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-07-authorized-fixture-abi-observation.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-07-authorized-fixture-abi-observation-evidence.v1.yaml"
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
PLAN = ROOT / "PLAN.md"
CHARTER_SCHEMA = "sipi.p4b-07.authorized-fixture-abi-observation.v1"
EVIDENCE_SCHEMA = "sipi.p4b-07.authorized-fixture-abi-observation-evidence.v1"

TX_DLL = "05d299826a9c69ae8ac3d236d88adcad5860fc7e229243f1541d1734b8ed28ea"
RX_DLL = "88a284f0967ad332f6230a8c5e791f47e9d22a05ae6778426c35707a18a3ab63"


class ObservationError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ObservationError("document_not_mapping")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != CHARTER_SCHEMA or charter.get("status") != "authorized_fixture_abi_observation_specified":
        raise ObservationError("charter_schema_or_status_invalid")
    probes = charter.get("probe_matrix")
    if not isinstance(probes, list) or len(probes) != 4:
        raise ObservationError("probe_matrix_invalid")
    if charter.get("probe_inputs") != {
        "sample_interval_s": 1e-12,
        "bit_time_s": 31.25e-12,
        "matrix": "identity_like_4x4",
        "waveform": "alternating_plus_minus_one",
        "clock_sentinel": -1.0,
    }:
        raise ObservationError("probe_inputs_drift")
    if charter.get("custody") != {"copies": 2, "identity": "byte_exact_reproduced", "cleanup": "verified_before_evidence"}:
        raise ObservationError("custody_drift")
    if charter.get("admission") != {
        "worker_admission": False,
        "product_runtime_invoked": False,
        "numerical_parity": False,
        "ibis_ami_compatibility": False,
        "tx_rx_composition": False,
        "release_evidence": False,
    }:
        raise ObservationError("admission_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != EVIDENCE_SCHEMA or evidence.get("status") != "two_fresh_custody_identity_reproduced_raw_output_hash_only":
        raise ObservationError("evidence_schema_or_status_invalid")
    entries = {entry.get("dll_id"): entry for entry in evidence.get("entries", [])}
    tx = entries.get("ads-pcie-gen5-tx-dll")
    rx = entries.get("ads-pcie-gen5-rx-dll")
    if tx is None or rx is None:
        raise ObservationError("evidence_entries_incomplete")
    if tx.get("dll_sha256") != TX_DLL or rx.get("dll_sha256") != RX_DLL:
        raise ObservationError("evidence_dll_hash_drift")
    if tx.get("custody_identity") != "byte_exact_reproduced" or rx.get("custody_identity") != "byte_exact_reproduced":
        raise ObservationError("custody_identity_drift")
    statuses = tx.get("probe_statuses", {})
    if any(status != "success" for status in statuses.values()):
        raise ObservationError("tx_probe_status_drift")
    claims = evidence.get("non_claims")
    expected = ["not_numerical_parity", "not_ibis_ami_compatibility", "not_tx_rx_composition", "not_worker_admission", "not_product_runtime", "not_rx_init_stability", "not_release_evidence"]
    if not isinstance(claims, list) or claims != expected:
        raise ObservationError("non_claims_drift")
    registry = load_yaml(REGISTRY)
    registered = {material["id"]: material for material in registry.get("materials", [])}
    for material_id in ("ads-pcie-gen5-tx-dll", "ads-pcie-gen5-rx-dll"):
        material = registered.get(material_id)
        if material is None or material.get("sha256") != entries[material_id]["dll_sha256"]:
            raise ObservationError(f"registry_dll_hash_mismatch:{material_id}")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-07a" not in plan_text:
        raise ObservationError("plan_row_missing")
    return {"valid": True, "tx_probes": len(statuses), "rx_probes": len(rx.get("probe_statuses", {}))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": CHARTER_SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ObservationError as error:
        print(json.dumps({"schema": CHARTER_SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
