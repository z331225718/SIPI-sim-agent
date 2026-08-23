"""Aggregate two fresh archive-only PB-04/PB-05 Python-reference runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from pb_03_replay_common import ROOT, compare_windows_pe_custody, sha256, windows_pe_custody_shape, windows_pe_repro_policy


MANIFESTS = {
    "PB-04": ROOT / "docs/baselines/pb-04-python-external-d3154093.v1.yaml",
    "PB-05": ROOT / "docs/baselines/pb-05-python-external-d3154093.v1.yaml",
}
AUDITS = {
    "PB-04": ROOT / "docs/baselines/audits/2026-08-24-pb-04-python-external-d3154093.md",
    "PB-05": ROOT / "docs/baselines/audits/2026-08-24-pb-05-python-external-d3154093.md",
}


def manifest_binding(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    core = {key: item for key, item in value.items() if key not in {"evidence", "harness", "verification", "audit"}}
    return sha256(json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def aggregate(row: str, first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    reports = [
        {"path": first_path.relative_to(ROOT).as_posix(), "sha256": sha256(first_path.read_bytes()), "run_id": first.get("run_id"), "fresh_run_nonce": first.get("fresh_run_nonce")},
        {"path": second_path.relative_to(ROOT).as_posix(), "sha256": sha256(second_path.read_bytes()), "run_id": second.get("run_id"), "fresh_run_nonce": second.get("fresh_run_nonce")},
    ]
    blockers: list[str] = []
    if first.get("row") != row or second.get("row") != row:
        blockers.append("report row drift")
    if first.get("schema") != "sipi.pb-04-05-python-external-replay.v1" or second.get("schema") != first.get("schema"):
        blockers.append("report schema drift")
    for key, label in (("candidate", "candidate identity"), ("upstream", "upstream identity"), ("fixture", "fixture identity"), ("toolchain", "toolchain identity")):
        if first.get(key) != second.get(key):
            blockers.append(f"{label} drift")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs are not independent")
    if first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
        blockers.append("fresh nonces are not independent")
    if reports[0]["sha256"] == reports[1]["sha256"]:
        blockers.append("report digests are not independent")
    if first.get("status") == "blocked" or second.get("status") == "blocked":
        blockers.append("at least one fresh external replay remains blocked")
    first_binary = first.get("build", {}).get("binary_sha256") if isinstance(first.get("build"), dict) else None
    second_binary = second.get("build", {}).get("binary_sha256") if isinstance(second.get("build"), dict) else None
    first_custody = first.get("build", {}).get("binary_custody") if isinstance(first.get("build"), dict) else None
    second_custody = second.get("build", {}).get("binary_custody") if isinstance(second.get("build"), dict) else None
    if not isinstance(first_custody, dict) or first_binary != first_custody.get("raw_sha256"):
        blockers.append("first raw binary digest is not bound to PE custody")
    if not isinstance(second_custody, dict) or second_binary != second_custody.get("raw_sha256"):
        blockers.append("second raw binary digest is not bound to PE custody")
    blockers.extend(compare_windows_pe_custody(first_custody, second_custody))
    manifest_path = MANIFESTS[row]
    audit_path = AUDITS[row]
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    result = {
        "schema": "sipi.pb-04-05-python-external-aggregate.v1",
        "version": 1,
        "row": row,
        "status": "passed" if not blockers else "blocked",
        "source_mode": "git_archive_at_candidate_prep_commit_plus_candidate_archive_fixture_copy_and_harness_snapshot",
        "reports": reports,
        "candidate": first.get("candidate"),
        "upstream": first.get("upstream"),
        "fixture": first.get("fixture"),
        "toolchain": first.get("toolchain"),
        "builds": [
            {"report": reports[0]["path"], "binary_sha256": first_binary, "binary_custody": first_custody},
            {"report": reports[1]["path"], "binary_sha256": second_binary, "binary_custody": second_custody},
        ],
        "manifest": {"path": manifest_path.relative_to(ROOT).as_posix(), "binding_sha256": manifest_binding(manifest)},
        "audit": {"path": audit_path.relative_to(ROOT).as_posix(), "sha256": sha256(audit_path.read_bytes())},
        "distinct_gate": {
            "unique_report_paths": reports[0]["path"] != reports[1]["path"],
            "unique_report_sha256": reports[0]["sha256"] != reports[1]["sha256"],
            "unique_run_ids": reports[0]["run_id"] != reports[1]["run_id"],
            "unique_fresh_run_nonces": reports[0]["fresh_run_nonce"] != reports[1]["fresh_run_nonce"],
            "exact_toolchain_identity": first.get("toolchain") == second.get("toolchain"),
            "exact_binary_sha256": first_binary == second_binary,
            "exact_binary_canonical_sha256": isinstance(first_custody, dict)
            and isinstance(second_custody, dict)
            and first_custody.get("canonical_sha256") == second_custody.get("canonical_sha256"),
        },
        "binary_custody_gate": {
            "raw_sha256_equal": first_binary == second_binary,
            "canonical_sha256_equal": isinstance(first_custody, dict)
            and isinstance(second_custody, dict)
            and first_custody.get("canonical_sha256") == second_custody.get("canonical_sha256"),
            "normalization_shape_equal": windows_pe_custody_shape(first_custody) == windows_pe_custody_shape(second_custody),
            "repro_policy": windows_pe_repro_policy(first_custody, second_custody),
            "blockers": compare_windows_pe_custody(first_custody, second_custody),
        },
        "claims": {
            "independent_python_reference": True,
            "same_crate_self_compare": False,
            "global_row_closed": False,
            "promotion": False,
            "release_approval": False,
        },
        "blockers": blockers,
        "non_claims": [
            "A pinned Python BackendRunResult artifact is an external oracle observation, not a release promotion.",
            "PB-04 selection and PB-05 payload compare remain fail-closed until the complete result contract is accepted.",
            "Raw PE digests may differ when only approved timestamp/RSDS-GUID fields differ; canonical digest, profile/normalization shape, or REPRO payload drift blocks aggregation and never promotes a row.",
        ],
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", choices=("PB-04", "PB-05"), required=True)
    parser.add_argument("--report-one", type=Path, required=True)
    parser.add_argument("--report-two", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.row, args.report_one.resolve(), args.report_two.resolve(), args.output.resolve())
    print(json.dumps({"row": args.row, "status": result["status"]}, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
