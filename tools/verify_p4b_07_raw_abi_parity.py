"""Fail closed on the P4B-07b TX raw ABI output parity.

The charter fixes the parity rule; the evidence records the two-fresh-
custody host-vs-ctypes-observer equality for all four TX probes. The
verifier binds charter, evidence, the observation evidence ref, the
registry TX hash, and the PLAN P4B-07b row; any drift fails closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-07-raw-abi-parity.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-07-raw-abi-parity-evidence.v1.yaml"
OBSERVATION = ROOT / "docs" / "baselines" / "p4b-07-authorized-fixture-abi-observation-evidence.v1.yaml"
OBSERVER = ROOT / "tools" / "p4b_07_ctypes_observer.py"
PLAN = ROOT / "PLAN.md"
CHARTER_SCHEMA = "sipi.p4b-07.raw-abi-parity.v1"
EVIDENCE_SCHEMA = "sipi.p4b-07.raw-abi-parity-evidence.v1"
TX_DLL = "05d299826a9c69ae8ac3d236d88adcad5860fc7e229243f1541d1734b8ed28ea"


class ParityError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParityError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != CHARTER_SCHEMA or charter.get("status") != "tx_raw_abi_parity_specified":
        raise ParityError("charter_schema_or_status_invalid")
    if charter.get("observer") != {"kind": "ctypes_external_only", "path": "tools/p4b_07_ctypes_observer.py", "product_code": False}:
        raise ParityError("observer_drift")
    if charter.get("parity_rule") != "per_probe_output_waveform_hash_len_and_clocks_hash_len_equal":
        raise ParityError("parity_rule_drift")
    if charter.get("admission") != {
        "rx_parity": False,
        "numerical_reference_parity": False,
        "ibis_ami_compatibility": False,
        "tx_rx_composition": False,
        "worker_admission": False,
        "product_runtime_invoked": False,
        "release_evidence": False,
    }:
        raise ParityError("admission_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != EVIDENCE_SCHEMA or evidence.get("status") != "tx_raw_abi_parity_reproduced_hash_only":
        raise ParityError("evidence_schema_or_status_invalid")
    if evidence.get("dll_sha256") != TX_DLL:
        raise ParityError("evidence_dll_hash_drift")
    if evidence.get("probe_parity") != "all_probes_host_equals_observer":
        raise ParityError("probe_parity_drift")
    for custody in ("custody_0_parity", "custody_1_parity"):
        parity = evidence.get(custody)
        if not isinstance(parity, dict) or len(parity) != 4 or not all(parity.values()):
            raise ParityError(f"{custody}_drift")
    if not OBSERVER.is_file():
        raise ParityError("observer_missing")
    if not OBSERVATION.is_file():
        raise ParityError("observation_evidence_missing")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-07b" not in plan_text:
        raise ParityError("plan_row_missing")
    return {"valid": True, "probes": 4, "custodies": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": CHARTER_SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ParityError as error:
        print(json.dumps({"schema": CHARTER_SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
