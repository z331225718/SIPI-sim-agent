# -*- coding: utf-8 -*-
"""Fail closed on the P5-02l default-expression set resolver.

Charter fixes the multi-key resolution scope reusing P5-02j/k; cross-check
evidence binds product set-resolution against the oracle _resolve_default.
Verifier binds charter, source map, evidence, Rust tokens, PLAN P5-02l.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-02l-resolve-parameters-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-02l-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02l-resolve-parameters-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "resolve_parameters_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02l.resolve-parameters-stage.v1"
POLICY = "sipi.p5-02l.resolve-parameters.v1.default-set"


class ResolveParamsError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ResolveParamsError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "default_set_resolver_ported":
        raise ResolveParamsError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("multi_key_resolution") is not True or admission.get("reuse_default_resolver") is not True:
        raise ResolveParamsError("resolve_admission_drift")
    if admission.get("behavior_profile") is not False:
        raise ResolveParamsError("profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise ResolveParamsError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn resolve_default_set_v1",
        "pub enum ResolveParametersErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ResolveParamsError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-02l.resolve-parameters-crosscheck-evidence.v1":
        raise ResolveParamsError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ResolveParamsError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise ResolveParamsError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02l" not in plan_text:
        raise ResolveParamsError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ResolveParamsError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())