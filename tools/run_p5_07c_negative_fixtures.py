"""P5-07c negative fixture executions over the property checker.

For each documented negative case, mutates the canonical JSON v2 in
exactly one way and asserts the property checker reports failure.
The evidence records per-case pass (expected rejection) hash-bound;
this is the executable negative surface (anti-single-truth).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import run_p5_07b_canonical_json_properties as CHECK

V2 = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v2.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-07-negative-fixture-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-07.negative-fixture-evidence.v1"


def find_target(v2):
    for key, entry in v2["keys"].items():
        for index, default in enumerate(entry.get("defaults", [])):
            if default.get("kind") in ("literal", "string_literal", "inf_literal", "resolved_reference", "statically_evaluated", "needs_matlab_oracle"):
                return key, index
    return None, None


CASES = [
    ("bad_kind", lambda v2, key, index: v2["keys"][key]["defaults"][index].__setitem__("kind", "bogus")),
    ("literal_nonfinite", lambda v2, key, index: v2["keys"][key]["defaults"][index].update({"kind": "literal", "value": "NaN"})),
    ("literal_unparsable", lambda v2, key, index: v2["keys"][key]["defaults"][index].update({"kind": "literal", "value": "abc"})),
    ("string_literal_unquoted", lambda v2, key, index: v2["keys"][key]["defaults"][index].update({"kind": "string_literal", "expression": "MM"})),
    ("inf_literal_invalid", lambda v2, key, index: v2["keys"][key]["defaults"][index].update({"kind": "inf_literal", "expression": "infinity"})),
    ("evaluated_no_value", lambda v2, key, index: (v2["keys"][key]["defaults"][index].update({"kind": "statically_evaluated"}), v2["keys"][key]["defaults"][index].pop("value", None))),
    ("oracle_no_expression", lambda v2, key, index: (v2["keys"][key]["defaults"][index].update({"kind": "needs_matlab_oracle"}), v2["keys"][key]["defaults"][index].pop("expression", None))),
    ("resolved_incomplete", lambda v2, key, index: v2["keys"][key]["defaults"][index].update({"kind": "resolved_reference", "value": "1.0"})),
    ("bad_required", lambda v2, key, index: v2["keys"][key]["defaults"][index].__setitem__("required", "maybe")),
    ("empty_entry", lambda v2, key, index: v2["keys"][key].__setitem__("defaults", [])),
]


def main() -> int:
    v2 = yaml.safe_load(V2.read_text(encoding="utf-8"))
    results = []
    failed_cases = 0
    for case_id, mutate in CASES:
        mutated = copy.deepcopy(v2)
        key, index = find_target(mutated)
        if key is None:
            raise SystemExit("no target for " + case_id)
        mutate(mutated, key, index)
        properties = CHECK.check_properties(mutated)
        expected_rejection = bool(properties["failures"])
        if not expected_rejection:
            failed_cases += 1
        results.append({"case": case_id, "rejected": expected_rejection, "failure_count": len(properties["failures"])})
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "negative_fixtures_all_rejected" if failed_cases == 0 else "negative_fixture_rejection_failed",
        "source_ref": "docs/baselines/p5-r480-canonical-parameter-json.v2.yaml",
        "source_sha256": v2.get("source_sha256"),
        "case_count": len(CASES),
        "results": results,
        "non_claims": [
            "not_a_compare",
            "not_product_validation",
            "not_release_evidence",
        ],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print("cases=" + str(len(CASES)) + " rejected=" + str(len(CASES) - failed_cases) + " failed=" + str(failed_cases))
    print("negative evidence written: " + str(EVIDENCE))
    return 0 if failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
