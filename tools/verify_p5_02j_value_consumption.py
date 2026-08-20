"""Fail closed on the P5-02j value-consumption / default-resolution stage port.

The charter fixes the scalar-catalog scope and admission; the source map
records the MIT function mapping; the cross-check evidence binds product
resolver and agent-com _resolve_default results. The verifier binds charter,
source map, evidence, Rust tokens, and the PLAN P5-02j row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-02j-default-resolution-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-02j-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02j-default-resolution-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "value_consumption_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02j.default-resolution-stage.v1"
POLICY = "sipi.p5-02j.value-consumption.v1.default-resolution"


class ValueConsumptionError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueConsumptionError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "default_resolution_scalar_catalog_ported":
        raise ValueConsumptionError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("scalar_literals") is not True or admission.get("derived_scalar_arithmetic") is not True:
        raise ValueConsumptionError("scalar_admission_drift")
    if admission.get("dfe_lower_limit_special") is not True:
        raise ValueConsumptionError("dfe_admission_drift")
    if admission.get("vector_matrix_defaults") is not False:
        raise ValueConsumptionError("vector_admission_drift")
    if admission.get("behavior_profile") is not False:
        raise ValueConsumptionError("profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 5:
        raise ValueConsumptionError("source_map_mapping_drift")
    if "vector/matrix default layout (snpPortsOrder, R_diepad, ts_sample_adj_range, string-matrix pkg_Z_c)" not in source_map.get("not_ported", []):
        raise ValueConsumptionError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn resolve_default_value_v1",
        "pub enum ResolvedDefaultV1",
        "pub enum ConsumptionErrorV1",
        "pub const VALUE_CONSUMPTION_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ValueConsumptionError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-02j.value-consumption-crosscheck-evidence.v1":
        raise ValueConsumptionError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ValueConsumptionError("evidence_status_drift")
    cases = evidence.get("cases", [])
    if len(cases) < 19 or evidence.get("matched_count") != evidence.get("case_count"):
        raise ValueConsumptionError("evidence_entry_mismatch")
    for case in cases:
        if not case.get("matched"):
            raise ValueConsumptionError("evidence_unmatched_case")
    if evidence.get("array_out_of_scope", {}).get("snp_port_order", {}).get("oracle_size") != 4:
        raise ValueConsumptionError("array_out_of_scope_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02j" not in plan_text:
        raise ValueConsumptionError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ValueConsumptionError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
