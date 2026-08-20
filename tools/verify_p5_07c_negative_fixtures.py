"""Fail closed on the P5-07c negative fixture evidence.

Each negative case mutates the canonical JSON v2 once and must be
rejected by the property checker. The verifier binds case count,
all-rejected state, source hash, and the PLAN P5-07c row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-07-negative-fixture-evidence.v1.yaml"
V2 = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v2.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-07.negative-fixture-evidence.v1"
CASE_COUNT = 10


class NegativeError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NegativeError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != SCHEMA or evidence.get("status") != "negative_fixtures_all_rejected":
        raise NegativeError("evidence_schema_or_status_invalid")
    if evidence.get("case_count") != CASE_COUNT:
        raise NegativeError("case_count_drift")
    results = evidence.get("results")
    if not isinstance(results, list) or len(results) != CASE_COUNT:
        raise NegativeError("results_drift")
    for result in results:
        if not result.get("rejected"):
            raise NegativeError("case_not_rejected:" + str(result.get("case")))
    v2 = load_yaml(V2)
    if evidence.get("source_sha256") != v2.get("source_sha256"):
        raise NegativeError("source_hash_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-07c" not in plan_text:
        raise NegativeError("plan_row_missing")
    return {"valid": True, "cases": CASE_COUNT}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except NegativeError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
