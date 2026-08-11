"""Verify current-candidate CLI evidence for the selected matched-S21 profile.

The historical CLI attestation remains immutable. This wrapper applies the
same strict report and source-tree checks to the current product candidate.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

from verify_channel_s2p_matched_acceptance import _load
from verify_channel_s2p_matched_cli_external_compare_evidence import (
    EvidenceError,
    NON_CLAIMS,
    SCHEMA as HISTORICAL_SCHEMA,
    verify_document as verify_historical_shape,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.s2p-matched.cli-current-external-compare-evidence.v1"
EVIDENCE = ROOT / "docs" / "baselines" / "channel-s2p-matched-cli-current-external-compare-evidence.v1.yaml"


def verify_document(document: object, report_path: Path | None = None) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise EvidenceError("current_evidence_schema_invalid")
    historical_shape = copy.deepcopy(document)
    historical_shape["schema"] = HISTORICAL_SCHEMA
    result = verify_historical_shape(historical_shape, report_path)
    return {
        "schema": SCHEMA,
        "valid": result["valid"],
        "profile_id": result["profile_id"],
        "report_bound": result["report_bound"],
        "evidence_level": "fresh_report_bound" if report_path is not None else "hash_only_attestation",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        result = verify_document(_load(arguments.evidence), arguments.report)
    except (EvidenceError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
