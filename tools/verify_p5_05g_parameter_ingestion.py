# -*- coding: utf-8 -*-
"""Verify the narrow P5-05g workbook-to-DTO product consumer."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-05g-com-parameter-ingestion-stage.v1.yaml"
AUDIT = ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p5-05g-com-parameter-ingestion.md"
AUDIT_RELATIVE = "docs/baselines/audits/2026-08-21-p5-05g-com-parameter-ingestion.md"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "com_parameter_ingestion_v1.rs"
SCHEMA = "sipi.p5-05g.com-parameter-ingestion-stage.v1"
POLICY = "sipi.p5-05g.com-parameter-ingestion-v1.workbook-to-dto-report"


class ParameterIngestionError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterIngestionError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "implemented_self_tested":
        raise ParameterIngestionError("charter_schema_or_status_invalid")
    if charter.get("policy") != POLICY:
        raise ParameterIngestionError("charter_policy_invalid")
    implementation = charter.get("implementation")
    if not isinstance(implementation, dict):
        raise ParameterIngestionError("implementation_missing")
    source = SOURCE if SOURCE.is_absolute() else root / SOURCE
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if implementation.get("sha256") != source_hash:
        raise ParameterIngestionError("source_hash_drift")
    required = (
        "pub fn ingest_com_parameters_v1",
        "ComParameterConsumptionReportV1",
        "validate_surface_partition",
        "merge_com_parameters_v1",
        "lookup_optional_v1",
        "SurfaceMismatch",
        "InexactWorkbookInteger",
        "UnsupportedWorkbookShape",
        "fold_key",
        "defaulted_keys",
        "unconsumed_keys",
        POLICY,
    )
    source_text = source_bytes.decode("utf-8")
    if any(token not in source_text for token in required):
        raise ParameterIngestionError("implementation_binding_drift")
    audit = charter.get("audit")
    if not isinstance(audit, dict):
        raise ParameterIngestionError("audit_metadata_missing")
    if audit.get("path") != AUDIT_RELATIVE:
        raise ParameterIngestionError("audit_path_drift")
    if not AUDIT.is_file():
        raise ParameterIngestionError("audit_missing")
    audit_hash = hashlib.sha256(AUDIT.read_bytes()).hexdigest()
    if audit.get("sha256") != audit_hash:
        raise ParameterIngestionError("audit_hash_drift")
    non_claims = charter.get("non_claims")
    required_non_claims = {
        "not_authoritative_com_oracle",
        "not_full_r480_parameter_contract",
        "not_profile_acceptance",
        "not_ieee_certification",
        "not_release_evidence",
    }
    if not isinstance(non_claims, list) or not required_non_claims.issubset(non_claims):
        raise ParameterIngestionError("non_claims_incomplete")
    return {
        "source_sha256": source_hash,
        "audit_sha256": audit_hash,
        "test_count": implementation.get("test_count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ParameterIngestionError as error:
        print(
            json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
