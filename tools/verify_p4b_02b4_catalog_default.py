# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b4 catalog-default validity core.

Charter fixes the profile-agnostic default-validity scope; cross-check
evidence binds product default validity against an independent reference.
Verifier binds charter, source map, evidence, Rust tokens, PLAN P4B-02b4.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b4-catalog-default-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b4-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b4-catalog-default-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "catalog_default_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b4.catalog-default-stage.v1"
POLICY = "sipi.p4b-02b4.catalog-default.v1.validity"


class CatalogDefaultError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CatalogDefaultError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "catalog_default_validity_ported":
        raise CatalogDefaultError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("default_token_validity") is not True or admission.get("materialize_typed_default") is not True:
        raise CatalogDefaultError("default_admission_drift")
    if admission.get("ami_runtime") is not False or admission.get("reserved_name_catalog") is not False:
        raise CatalogDefaultError("runtime_or_reserved_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise CatalogDefaultError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn token_valid_for_type_v1",
        "pub fn validate_catalog_defaults_v1",
        "pub fn materialize_default_v1",
        "pub enum CatalogDefaultErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise CatalogDefaultError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b4.catalog-default-crosscheck-evidence.v1":
        raise CatalogDefaultError("evidence_schema_invalid")
    if evidence.get("status") != "product_owned_self_crosscheck_unbound":
        raise CatalogDefaultError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise CatalogDefaultError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b4" not in plan_text:
        raise CatalogDefaultError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CatalogDefaultError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())