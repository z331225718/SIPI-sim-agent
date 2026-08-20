# -*- coding: utf-8 -*-
"""Fail closed on the P5-06d canonical normalized-input key signature core.

Charter fixes the profile-agnostic sorted-signature preflight scope;
cross-check evidence binds the product canonical signature and digest against
an independent Python reference and the authoritative P5-06c surface.
Verifier binds charter, source map, evidence, Rust tokens, PLAN P5-06d.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-06d-canonical-input-keys-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-06d-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06d-canonical-input-keys-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "canonical_input_keys_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-06d.canonical-input-keys-stage.v1"
POLICY = "sipi.p5-06d.canonical-input-keys.v1.sorted-signature"


class CanonicalInputKeysError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CanonicalInputKeysError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "canonical_input_keys_ported":
        raise CanonicalInputKeysError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("sorted_canonical_signature", "deterministic_order_free_digest",
               "in_config_key_extraction", "empty_key_value_duplicate_fail_closed")
    if any(admission.get(k) is not True for k in claimed):
        raise CanonicalInputKeysError("delivered_admission_drift")
    if admission.get("compare_matrix") is not False or admission.get("metric_derivation") is not False:
        raise CanonicalInputKeysError("compare_or_metric_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 5:
        raise CanonicalInputKeysError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn canonical_input_keys_v1",
        "pub enum CanonicalInputKeysErrorV1",
        "DuplicateKey",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise CanonicalInputKeysError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-06d.canonical-input-keys-crosscheck-evidence.v1":
        raise CanonicalInputKeysError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise CanonicalInputKeysError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise CanonicalInputKeysError("evidence_entry_mismatch")
    happy = [e for e in evidence["entries"] if e.get("product_ok") and e["reference_ok"]]
    failure = [e for e in evidence["entries"] if not e.get("product_ok") and not e["reference_ok"]]
    if not happy or not failure:
        raise CanonicalInputKeysError("evidence_not_exercising_both_paths")
    surface = [e for e in evidence["entries"] if e["label"] == "authoritative_in_config_surface"]
    if not surface or not surface[0].get("matched") or surface[0].get("surface_in_config_count") != 82:
        raise CanonicalInputKeysError("authoritative_surface_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-06d" not in plan_text:
        raise CanonicalInputKeysError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CanonicalInputKeysError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
