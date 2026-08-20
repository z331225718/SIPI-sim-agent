"""P5-06b external-only oracle metric-surface parser.

Reads the P5-06a evidence summary_content and records the structured
metric surface: network roles and keys, output metric keys, per-case
checkpoint keys, and case count, hash-bound to the oracle run.
No comparison, normalization, or product derivation is performed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06-matlab-oracle-first-run-evidence.v1.yaml"
SURFACE = ROOT / "docs" / "baselines" / "p5-06-oracle-metric-surface.v1.yaml"
SURFACE_SCHEMA = "sipi.p5-06.oracle-metric-surface.v1"


def main() -> int:
    evidence = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))
    summary = json.loads(evidence["summary_content"])
    network_roles = [entry.get("role") for entry in summary.get("network_metrics", [])]
    network_keys = sorted({key for entry in summary.get("network_metrics", []) for key in entry if key != "role"})
    output_keys = sorted(summary.get("output_metrics", {}).keys())
    case_count = summary.get("case_count", 0)
    checkpoint_keys = sorted({
        key
        for case in summary.get("case_metrics", [])
        for key in case.get("internal_checkpoints", {})
    })
    case_output_keys = sorted({
        key
        for case in summary.get("case_metrics", [])
        for key in case.get("output_metrics", {})
    })
    surface = {
        "schema": SURFACE_SCHEMA,
        "status": "oracle_metric_surface_observed_hash_bound",
        "evidence_ref": "docs/baselines/p5-06-matlab-oracle-first-run-evidence.v1.yaml",
        "source_sha256": evidence.get("output_file_hashes", {}).get("summary.json"),
        "case_count": case_count,
        "network_roles": network_roles,
        "network_keys": network_keys,
        "output_metric_keys": output_keys,
        "case_output_metric_keys": case_output_keys,
        "checkpoint_keys": checkpoint_keys,
        "non_claims": [
            "not_a_compare",
            "not_normalized_input_verified",
            "not_warnings_contract",
            "not_release_evidence",
        ],
    }
    SURFACE.write_text(yaml.safe_dump(surface, sort_keys=False), encoding="utf-8")
    print("roles=" + str(network_roles) + " output_keys=" + str(len(output_keys)) + " checkpoints=" + str(checkpoint_keys))
    print("surface written: " + str(SURFACE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
