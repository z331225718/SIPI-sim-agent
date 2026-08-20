"""P5-07b canonical parameter JSON property surface.

Mechanical property checks over the oracle-derived canonical JSON v2,
independent of MATLAB: well-formed default kinds, finite values,
consistent required flags, non-empty inventories. Result recorded
hash-bound as the property surface (anti-single-truth evidence).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v2.yaml"
PROPERTY = ROOT / "docs" / "baselines" / "p5-07-canonical-json-property-surface.v1.yaml"
PROPERTY_SCHEMA = "sipi.p5-07.canonical-json-property-surface.v1"

ALLOWED_KINDS = {"none", "literal", "inf_literal", "string_literal", "resolved_reference", "statically_evaluated", "needs_matlab_oracle"}
ALLOWED_REQUIRED = {"true", "false", "absent"}


def check_properties(v2):
    properties = {}
    failures = []
    total_calls = 0
    for key, entry in v2["keys"].items():
        if not entry.get("occurrences") or not entry.get("defaults"):
            failures.append("empty_entry:" + key)
        for default in entry.get("defaults", []):
            total_calls += 1
            kind = default.get("kind")
            if kind not in ALLOWED_KINDS:
                failures.append("bad_kind:" + key + ":" + str(kind))
            required = default.get("required")
            if required not in ALLOWED_REQUIRED:
                failures.append("bad_required:" + key + ":" + str(required))
            if kind == "literal":
                value = default.get("value")
                if value is None:
                    failures.append("literal_no_value:" + key)
                else:
                    lowered = value.lower()
                    is_bool = lowered in ("true", "false")
                    is_matrix = value.strip().startswith("[") and value.strip().endswith("]")
                    if not is_bool and not is_matrix:
                        try:
                            parsed = float(value)
                            if parsed != parsed or parsed in (float("inf"), float("-inf")):
                                failures.append("literal_nonfinite:" + key)
                        except ValueError:
                            failures.append("literal_unparsable:" + key)
            if kind == "inf_literal":
                if default.get("expression") not in ("inf", "+inf", "-inf"):
                    failures.append("inf_literal_invalid:" + key)
            if kind == "string_literal":
                expression = default.get("expression")
                if not (isinstance(expression, str) and expression.startswith("\'") and expression.endswith("\'")):
                    failures.append("string_literal_unquoted:" + key)
            if kind == "resolved_reference":
                if default.get("value") is None or not default.get("chain"):
                    failures.append("resolved_incomplete:" + key)
            if kind == "statically_evaluated":
                if default.get("value") is None:
                    failures.append("evaluated_no_value:" + key)
            if kind == "needs_matlab_oracle":
                if not default.get("expression"):
                    failures.append("oracle_no_expression:" + key)
    properties["total_calls"] = total_calls
    properties["keys"] = len(v2["keys"])
    properties["failures"] = failures
    properties["pass"] = not failures
    return properties


def main() -> int:
    v2 = yaml.safe_load(V2.read_text(encoding="utf-8"))
    properties = check_properties(v2)
    property_doc = {
        "schema": PROPERTY_SCHEMA,
        "status": "canonical_json_properties_checked" if not properties["failures"] else "canonical_json_properties_failed",
        "source_ref": "docs/baselines/p5-r480-canonical-parameter-json.v2.yaml",
        "source_sha256": v2.get("source_sha256"),
        "properties": properties,
        "non_claims": [
            "not_a_compare",
            "not_matlab_cross_check",
            "not_release_evidence",
        ],
    }
    PROPERTY.write_text(yaml.safe_dump(property_doc, sort_keys=False), encoding="utf-8")
    print("calls=" + str(properties["total_calls"]) + " failures=" + str(len(properties["failures"])))
    print("property surface written: " + str(PROPERTY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
