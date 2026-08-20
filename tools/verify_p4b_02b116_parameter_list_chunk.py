# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b116 parameter list chunking core.

Charter fixes the fixed-size chunking scope; cross-check evidence binds product chunking
against an independent reference. Verifier binds charter, source map, evidence, Rust tokens,
PLAN P4B-02b116.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b116-parameter-list-chunk-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b116-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b116-parameter-list-chunk-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_list_chunk_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b116.parameter-list-chunk-stage.v1"
POLICY = "sipi.p4b-02b116.parameter-list-chunk-v1.fixed-size-chunking"


class ParameterListChunkError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterListChunkError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_list_chunk_ported":
        raise ParameterListChunkError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("fixed_size_chunking", "remainder_chunk", "zero_chunk_size_fail_closed")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterListChunkError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise ParameterListChunkError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn chunk_parameter_list_v1",
        "pub enum ParameterListChunkErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterListChunkError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b116-parameter-list-chunk-crosscheck-evidence.v1":
        raise ParameterListChunkError("evidence_schema_invalid")
    if evidence.get("status") != "product_owned_self_crosscheck_unbound":
        raise ParameterListChunkError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise ParameterListChunkError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b116" not in plan_text:
        raise ParameterListChunkError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
    except ParameterListChunkError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}))
        return 1
    print(json.dumps({"schema": SCHEMA, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
