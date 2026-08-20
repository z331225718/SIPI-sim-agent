"""Fail closed on the P4B-08a authorized S4P structure observation.

The evidence records the six authorized S4P files' record counts,
continuation structure, field layout, and Hz axis endpoints, hash-bound
to the registry. The verifier binds file set, hashes, structure facts,
and the PLAN P4B-08a row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-08-s4p-observation-evidence.v1.yaml"
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-08.s4p-observation-evidence.v1"
S4P_IDS = ["ads-pcie-gen5-s4p-tx-typ", "ads-pcie-gen5-s4p-tx-fast", "ads-pcie-gen5-s4p-tx-slow",
           "ads-pcie-gen5-s4p-rx-typ", "ads-pcie-gen5-s4p-rx-fast", "ads-pcie-gen5-s4p-rx-slow"]


class S4PObservationError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S4PObservationError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != SCHEMA or evidence.get("status") != "authorized_s4p_structures_observed_hz_axis_hash_bound":
        raise S4PObservationError("evidence_schema_or_status_invalid")
    files = {entry.get("material_id"): entry for entry in evidence.get("files", [])}
    if set(files) != set(S4P_IDS):
        raise S4PObservationError("file_set_drift")
    registry = load_yaml(REGISTRY)
    registered = {m["id"]: m for m in registry.get("materials", [])}
    for material_id in S4P_IDS:
        entry = files.get(material_id)
        material = registered.get(material_id)
        if entry is None or material is None:
            raise S4PObservationError(f"missing:{material_id}")
        if entry.get("sha256") != material.get("sha256", "").lower():
            raise S4PObservationError(f"hash_drift:{material_id}")
        if entry.get("first_record_fields") != 9:
            raise S4PObservationError(f"field_layout_drift:{material_id}")
        expected = 10003 if material_id.startswith("ads-pcie-gen5-s4p-tx") else 8003
        if entry.get("record_count") != expected:
            raise S4PObservationError(f"record_count_drift:{material_id}")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-08a" not in plan_text:
        raise S4PObservationError("plan_row_missing")
    return {"valid": True, "files": len(files)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except S4PObservationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
