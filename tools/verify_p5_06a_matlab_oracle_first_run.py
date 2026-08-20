"""Fail closed on the P5-06a MATLAB oracle first-run evidence.

The evidence records the first successful MATLAB r4.80 oracle run
(26.56 GHz, 120g C2M TP1a config, synthetic thru/fext/next) with
hash-bound outputs. The verifier binds evidence status, hashes, and the
PLAN P5-06a row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06-matlab-oracle-first-run-evidence.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-06.matlab-oracle-first-run-evidence.v1"


class OracleFirstRunError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OracleFirstRunError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != SCHEMA or evidence.get("status") != "matlab_oracle_first_run_succeeded_hash_bound":
        raise OracleFirstRunError("evidence_schema_or_status_invalid")
    if evidence.get("target_frequency_ghz") != 26.56:
        raise OracleFirstRunError("target_frequency_drift")
    hashes = evidence.get("output_file_hashes")
    if not isinstance(hashes, dict) or "matlab_oracle.mat" not in hashes or "summary.json" not in hashes:
        raise OracleFirstRunError("output_hashes_incomplete")
    for name, digest in hashes.items():
        if not isinstance(digest, str) or len(digest) != 64:
            raise OracleFirstRunError(f"output_hash_invalid:{name}")
    claims = evidence.get("non_claims")
    expected = ["not_a_product_runtime", "not_compute_parity", "not_release_evidence"]
    if not isinstance(claims, list) or claims != expected:
        raise OracleFirstRunError("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-06a" not in plan_text:
        raise OracleFirstRunError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except OracleFirstRunError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
