# -*- coding: utf-8 -*-
"""Fail closed on the P4A-03ad typed IBIS model selector keywords core.

Charter fixes the model selector keywords scope; cross-check evidence binds product
lifting against an independent reference. Verifier binds charter, source map,
evidence, Rust tokens, PLAN P4A-03ad.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4a-03ad-model-selector-keywords-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4a-03ad-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03ad-model-selector-keywords-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ibis" / "src" / "model_selector_keywords_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-03ad.model-selector-keywords-stage.v1"
POLICY = "sipi.p4a-03ad.model-selector-keywords-v1.typed-selector-keywords"


class ModelSelectorKeywordsError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ModelSelectorKeywordsError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "model_selector_keywords_ported":
        raise ModelSelectorKeywordsError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("typed_model_selector_keywords_declaration", "model_options_validation",
               "ascii_selector_name_validation", "fail_closed_on_invalid_input")
    if any(admission.get(k) is not True for k in claimed):
        raise ModelSelectorKeywordsError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise ModelSelectorKeywordsError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn lift_model_selector_keywords_v1",
        "pub struct TypedModelSelectorKeywordsV1",
        "ModelSelectorKeywordsErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ModelSelectorKeywordsError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4a-03ad.model-selector-keywords-crosscheck-evidence.v1":
        raise ModelSelectorKeywordsError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ModelSelectorKeywordsError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 3:
        raise ModelSelectorKeywordsError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-03ad" not in plan_text:
        raise ModelSelectorKeywordsError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ModelSelectorKeywordsError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
