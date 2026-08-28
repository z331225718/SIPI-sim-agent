"""Aggregate two fresh AS-03 power-wave solve replay reports."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_as_03_power_wave_solve_replay as replay


SCHEMA = "sipi.as-03-power-wave-solve-replay-aggregate.v1"


def _candidate_crossrun(value: dict[str, Any]) -> dict[str, Any]:
    per_build = {"binary_pre", "binary_post", "compiled_inputs_pre", "compiled_inputs_post"}
    return {key: item for key, item in value.items() if key not in per_build}


def _report(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve(strict=True)
    if resolved.parent != root or replay._is_reparse(path):
        raise ValueError("report must be a direct regular child of report root")
    payload = replay._read_regular(resolved, replay.MAX_REPORT_BYTES)
    value = json.loads(payload.decode("utf-8"))
    return replay.validate_report(value), payload


def validate_aggregate(value: Any) -> dict[str, Any]:
    root = replay._exact_keys(value, {"schema", "status", "work_item", "report_count", "reports", "shared", "numeric_change", "blockers", "claims", "non_claims"}, "aggregate")
    if root["schema"] != SCHEMA or root["status"] != "blocked_numeric_semantics" or root["work_item"] != "AS-03" or type(root["report_count"]) is not int or root["report_count"] != 2:
        raise ValueError("aggregate identity gate failed")
    if type(root["reports"]) is not list or len(root["reports"]) != 2:
        raise ValueError("aggregate report count drift")
    paths: set[str] = set()
    hashes: set[str] = set()
    run_ids: set[str] = set()
    nonces: set[str] = set()
    for index, raw in enumerate(root["reports"]):
        item = replay._exact_keys(raw, {"basename", "path_redacted", "bytes", "sha256", "nlink", "run_id", "nonce"}, f"reports[{index}]")
        if (
            type(item["basename"]) is not str
            or not item["basename"]
            or "/" in item["basename"]
            or "\\" in item["basename"]
            or item["path_redacted"] is not True
            or type(item["bytes"]) is not int
            or item["bytes"] <= 0
            or not replay._hex(item["sha256"], replay.HEX64)
            or type(item["nlink"]) is not int
            or item["nlink"] != 1
            or not replay._hex(item["nonce"], replay.HEX64)
            or type(item["run_id"]) is not str
            or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", item["run_id"]) is None
        ):
            raise ValueError("aggregate report receipt malformed")
        paths.add(item["basename"].casefold())
        hashes.add(item["sha256"])
        run_ids.add(item["run_id"])
        nonces.add(item["nonce"])
    if not all(len(values) == 2 for values in (paths, hashes, run_ids, nonces)):
        raise ValueError("fresh replay distinctness gate failed")
    shared = replay._exact_keys(root["shared"], {"prep_commit", "prep_tree", "prep_parent", "candidate_commit", "candidate_tree", "baseline_path", "baseline_candidate_commit", "baseline_candidate_tree", "upstream_commit", "upstream_tree", "scikit_rf_commit", "scikit_rf_tree", "toolchain", "fixture_sha256", "baseline_sha256"}, "shared")
    if shared["prep_parent"] != replay.EXPECTED_PREP_PARENT_COMMIT or shared["candidate_commit"] != replay.PRODUCTION_COMMIT or shared["candidate_tree"] != replay.PRODUCTION_TREE or shared["baseline_path"] != replay.BASELINE_PATH or shared["baseline_candidate_commit"] != replay.BASELINE_CANDIDATE_COMMIT or shared["baseline_candidate_tree"] != replay.BASELINE_CANDIDATE_TREE or shared["upstream_commit"] != replay.UPSTREAM_COMMIT or shared["upstream_tree"] != replay.UPSTREAM_TREE or shared["scikit_rf_commit"] != replay.SKRF_COMMIT or shared["scikit_rf_tree"] != replay.SKRF_TREE or shared["fixture_sha256"] != replay.FIXTURE_SHA256:
        raise ValueError("aggregate shared identity drift")
    numeric = replay._exact_keys(root["numeric_change"], {"prior", "current", "differing_components_change", "max_ulp_change", "numeric_parity", "blocked_numeric_semantics"}, "numeric_change")
    current = replay._exact_keys(numeric["current"], {"differing_components", "max_ulp", "differences", "committed_asserted_real_bits", "upstream_real_bits", "upstream_complex_matrix", "independent_complex_diagnostic"}, "numeric_change.current")
    replay._validate_difference_receipt({key: current[key] for key in ("differing_components", "max_ulp", "differences")}, "numeric_change.current")
    recomputed = replay._difference_real(current["committed_asserted_real_bits"], current["upstream_real_bits"])
    if {key: current[key] for key in ("differing_components", "max_ulp", "differences")} != recomputed or numeric["prior"] != {"differing_components": 4, "max_ulp": 4} or current["differing_components"] != 3 or current["max_ulp"] != 1 or numeric["differing_components_change"] != "4_to_3" or numeric["max_ulp_change"] != "4_to_1" or numeric["numeric_parity"] is not False or numeric["blocked_numeric_semantics"] is not True:
        raise ValueError("aggregate numeric gate failed")
    if root["blockers"] != ["blocked_numeric_semantics"]:
        raise ValueError("aggregate blocker drift")
    claims = replay._exact_keys(root["claims"], {"two_fresh_replays", "clean_production_archive_execution", "committed_real_checkpoint", "pinned_scikit_rf_leaf_execution", "agent_spice_source_replay", "complete_complex_checkpoint", "private_probe_injection", "numeric_parity", "s_parameter_fit"}, "claims")
    if claims != {"two_fresh_replays": True, "clean_production_archive_execution": True, "committed_real_checkpoint": True, "pinned_scikit_rf_leaf_execution": True, "agent_spice_source_replay": False, "complete_complex_checkpoint": False, "private_probe_injection": False, "numeric_parity": False, "s_parameter_fit": False}:
        raise ValueError("aggregate claim drift")
    if root["non_claims"] != ["candidate_complete_complex_checkpoint", "independent_probe_is_production_runtime", "agent_spice_yparam_path_execution", "numeric_parity", "acceptance_tolerance", "general_nudge_eig_equivalence", "s_parameter_fit", "AS-05_Xyce_XDM", "release_acceptance"]:
        raise ValueError("aggregate non-claims drift")
    return root


def aggregate(first_path: Path, second_path: Path, report_root: Path) -> dict[str, Any]:
    root = replay._safe_directory(report_root)
    first_resolved, second_resolved = first_path.resolve(strict=True), second_path.resolve(strict=True)
    if first_resolved == second_resolved:
        raise ValueError("replay report paths must be distinct")
    reports = []
    payloads = []
    for path in (first_resolved, second_resolved):
        report, payload = _report(path, root)
        reports.append(report)
        payloads.append(payload)
    first, second = reports
    if first["run_id"] == second["run_id"] or first["nonce"] == second["nonce"] or replay._sha256(payloads[0]) == replay._sha256(payloads[1]):
        raise ValueError("fresh replay identities/hashes must be distinct")
    shared_pairs = (
        ("prep", first["prep"], second["prep"]),
        ("candidate", _candidate_crossrun(first["candidate"]), _candidate_crossrun(second["candidate"])),
        ("baseline", first["baseline"], second["baseline"]),
        ("upstream", first["upstream"], second["upstream"]),
        ("scikit_rf", first["scikit_rf"], second["scikit_rf"]),
        ("toolchain", first["toolchain"], second["toolchain"]),
        ("fixture", first["fixture"], second["fixture"]),
        ("numeric_change", first["numeric_change"], second["numeric_change"]),
        ("blockers", first["blockers"], second["blockers"]),
        ("claims", first["claims"], second["claims"]),
        ("non_claims", first["non_claims"], second["non_claims"]),
    )
    for label, left, right in shared_pairs:
        if left != right:
            raise ValueError(f"fresh replay {label} drift")
    value = {
        "schema": SCHEMA,
        "status": "blocked_numeric_semantics",
        "work_item": "AS-03",
        "report_count": 2,
        "reports": [
            {"basename": path.name, "path_redacted": True, "bytes": len(payload), "sha256": replay._sha256(payload), "nlink": 1, "run_id": report["run_id"], "nonce": report["nonce"]}
            for path, payload, report in zip((first_resolved, second_resolved), payloads, reports, strict=True)
        ],
        "shared": {
            "prep_commit": first["prep"]["commit"],
            "prep_tree": first["prep"]["tree"],
            "prep_parent": first["prep"]["parent"],
            "candidate_commit": first["candidate"]["commit"],
            "candidate_tree": first["candidate"]["tree"],
            "baseline_path": first["baseline"]["path"],
            "baseline_candidate_commit": first["baseline"]["candidate_commit"],
            "baseline_candidate_tree": first["baseline"]["candidate_tree"],
            "upstream_commit": first["upstream"]["commit"],
            "upstream_tree": first["upstream"]["tree"],
            "scikit_rf_commit": first["scikit_rf"]["commit"],
            "scikit_rf_tree": first["scikit_rf"]["tree"],
            "toolchain": first["toolchain"],
            "fixture_sha256": first["fixture"]["sha256"],
            "baseline_sha256": first["baseline"]["sha256"],
        },
        "numeric_change": {key: first["numeric_change"][key] for key in ("prior", "current", "differing_components_change", "max_ulp_change", "numeric_parity", "blocked_numeric_semantics")},
        "blockers": ["blocked_numeric_semantics"],
        "claims": {"two_fresh_replays": True, "clean_production_archive_execution": True, "committed_real_checkpoint": True, "pinned_scikit_rf_leaf_execution": True, "agent_spice_source_replay": False, "complete_complex_checkpoint": False, "private_probe_injection": False, "numeric_parity": False, "s_parameter_fit": False},
        "non_claims": first["non_claims"],
    }
    validate_aggregate(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    parser.add_argument("--report-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    try:
        value = aggregate(Path(args.first), Path(args.second), Path(args.report_root))
        replay._write_json(Path(args.output), Path(args.output_root), value)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"AS-03 aggregate blocked: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
