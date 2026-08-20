# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b3 AMI parameter-catalog typed core.

Charter fixes profile-agnostic catalog scope; cross-check evidence binds
product catalog validation against an independent reference. Verifier
binds charter, source map, evidence, Rust tokens, PLAN P4B-02b3.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b3-parameter-catalog-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b3-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b3-parameter-catalog-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_catalog_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b3.parameter-catalog-stage.v1"
POLICY = "sipi.p4b-02b3.parameter-catalog.v1.typed"


class CatalogError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CatalogError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_catalog_core_ported":
        raise CatalogError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("catalog_compile") is not True or admission.get("usage_in_required") is not True:
        raise CatalogError("catalog_admission_drift")
    if admission.get("reserved_name_catalog") is not False or admission.get("ami_runtime") is not False:
        raise CatalogError("reserved_or_runtime_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise CatalogError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct CatalogEntryV1",
        "pub struct ParameterCatalogV1",
        "pub fn validate_candidate_set_v1",
        "pub enum AmiUsageV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise CatalogError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b3.parameter-catalog-crosscheck-evidence.v1":
        raise CatalogError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise CatalogError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise CatalogError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b3" not in plan_text:
        raise CatalogError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CatalogError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())