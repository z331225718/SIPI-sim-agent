# -*- coding: utf-8 -*-
"""Fail closed on the P4A-03f pin-to-model linkage core.

Charter fixes the profile-agnostic typed pin-model resolution scope;
cross-check evidence binds product linkage behaviour against an
independent reference. Verifier binds charter, source map, evidence, Rust
tokens, PLAN P4A-03f.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4a-03f-pin-model-linkage-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4a-03f-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03f-pin-model-linkage-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ibis" / "src" / "pin_model_linkage_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-03f.pin-model-linkage-stage.v1"
POLICY = "sipi.p4a-03f.pin-model-linkage.v1.typed"


class PinModelLinkageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PinModelLinkageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "pin_model_linkage_ported":
        raise PinModelLinkageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("pin_model_resolution", "marker_allowance", "unresolved_fail_closed", "deterministic_order", "profile_agnostic")
    if any(admission.get(k) is not True for k in claimed):
        raise PinModelLinkageError("delivered_admission_drift")
    if admission.get("electrical_semantics") is not False or admission.get("reserved_name_catalog") is not False:
        raise PinModelLinkageError("electrical_or_reserved_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise PinModelLinkageError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn resolve_pin_model_linkage_v1",
        "pub enum PinModelLinkageErrorV1",
        "UnresolvedModel",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise PinModelLinkageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4a-03f.pin-model-linkage-crosscheck-evidence.v1":
        raise PinModelLinkageError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise PinModelLinkageError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise PinModelLinkageError("evidence_entry_mismatch")
    happy = [e for e in evidence["entries"] if e.get("product_ok") and e["reference_ok"]]
    failure = [e for e in evidence["entries"] if not e.get("product_ok") and not e["reference_ok"]]
    if not happy or not failure:
        raise PinModelLinkageError("evidence_not_exercising_both_paths")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-03f" not in plan_text:
        raise PinModelLinkageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except PinModelLinkageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
