"""Fail closed on the P5-07b canonical JSON property surface.

The property surface records mechanical checks over the canonical JSON
v2 (well-formed kinds, finite values, quoted strings, inf literals,
consistent required flags). The verifier binds pass state, counts,
source hash, and the PLAN P5-07b row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROPERTY = ROOT / "docs" / "baselines" / "p5-07-canonical-json-property-surface.v1.yaml"
V2 = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v2.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-07.canonical-json-property-surface.v1"
TOTAL_CALLS = 229


class PropertyError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PropertyError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    document = load_yaml(PROPERTY)
    if document.get("schema") != SCHEMA or document.get("status") != "canonical_json_properties_checked":
        raise PropertyError("property_schema_or_status_invalid")
    properties = document.get("properties")
    if not isinstance(properties, dict) or not properties.get("pass"):
        raise PropertyError("property_failures_present")
    if properties.get("total_calls") != TOTAL_CALLS:
        raise PropertyError("total_calls_drift")
    v2 = load_yaml(V2)
    if document.get("source_sha256") != v2.get("source_sha256"):
        raise PropertyError("source_hash_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-07b" not in plan_text:
        raise PropertyError("plan_row_missing")
    return {"valid": True, "calls": TOTAL_CALLS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except PropertyError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
