"""Aggregate four v4 TP0V replay reports without turning them into evidence."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_com_tp0v_r2024b_v4_replay import (  # noqa: E402
    CANDIDATE_RECEIPT,
    CANDIDATE_GATE_PARENT,
    CASE_INDICES,
    PROHIBITED_TRANSFORMS,
    PACKAGE_TESTCASE_INDEX,
    RUN_IDS,
    SCHEMA as REPLAY_SCHEMA,
    SCALAR_NAMES,
    SELECTED_CASE_INDEX,
    SELECTED_PORT,
    UPSTREAM_RECEIPT,
    VECTOR_NAMES,
    compare_scalar,
    compare_vectors,
    exact_repeat,
    repeat_payload_exact,
    sha256_bytes,
    sha256_file,
)


SCHEMA = "sipi.com.tp0v-r2024b-v4-aggregate.v1"
NONCE_RE = re.compile(r"^[0-9a-f]{64}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical_digest(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _receipt_equal(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == expected.get(key) for key in ("commit", "tree", "archive_sha256", "archive_bytes"))


def _validate_runtime_report(report: dict[str, Any], expected_id: str) -> list[str]:
    require(report.get("schema") == REPLAY_SCHEMA, f"{expected_id}: replay schema")
    require(report.get("diagnostic_only") is True and report.get("formal_record") is False, f"{expected_id}: diagnostic-only gate")
    require(report.get("run_id") == expected_id, f"{expected_id}: run id")
    require(report.get("engine") in {"matlab", "rust"}, f"{expected_id}: engine")
    require((report["engine"] == "matlab") == expected_id.startswith("matlab"), f"{expected_id}: engine/run id mismatch")
    require(isinstance(report.get("nonce"), str) and NONCE_RE.fullmatch(report["nonce"]) is not None, f"{expected_id}: nonce")
    require(_receipt_equal(report.get("candidate", {}), CANDIDATE_RECEIPT), f"{expected_id}: candidate receipt")
    require(report.get("candidate_gate_parent") == CANDIDATE_GATE_PARENT, f"{expected_id}: candidate gate parent")
    require(_receipt_equal(report.get("upstream", {}), UPSTREAM_RECEIPT), f"{expected_id}: upstream receipt")
    require(report.get("comparison_contract", {}).get("vectors") == list(VECTOR_NAMES), f"{expected_id}: vector contract")
    require(report.get("comparison_contract", {}).get("prohibited_transforms") == list(PROHIBITED_TRANSFORMS), f"{expected_id}: transform contract")
    contract = report.get("comparison_contract", {})
    expected_case_to_port = [{"case_index": SELECTED_CASE_INDEX, "port": SELECTED_PORT, "package_testcase_index": PACKAGE_TESTCASE_INDEX}]
    require(contract.get("scalar_case_scope") == {"selected_case_index": SELECTED_CASE_INDEX, "package_testcase_index": PACKAGE_TESTCASE_INDEX, "case_count": len(CASE_INDICES)}, f"{expected_id}: scalar case scope")
    require(contract.get("selected_case_index") == SELECTED_CASE_INDEX, f"{expected_id}: selected case")
    require(contract.get("package_testcase_index") == PACKAGE_TESTCASE_INDEX, f"{expected_id}: package testcase")
    require(contract.get("selected_port") == SELECTED_PORT and contract.get("case_to_port") == expected_case_to_port, f"{expected_id}: case/port binding")
    d3 = report.get("d3")
    require(isinstance(d3, dict) and d3.get("status") == "not_evaluated_configuration_disables_tdiln", f"{expected_id}: D3 policy")
    require(d3.get("global_d3_enabled") is True, f"{expected_id}: global D3 must remain enabled")
    selected = d3.get("selected_configs")
    require(isinstance(selected, list) and selected and all(item.get("COMPUTE_TDILN") == 0 for item in selected), f"{expected_id}: selected D3 config")
    roots = report.get("roots")
    require(isinstance(roots, dict) and roots.get("path_redacted") is True, f"{expected_id}: root custody")
    root_labels = [roots.get("candidate"), roots.get("build"), *(roots.get("repeats") or [])]
    require(all(isinstance(item, str) and item for item in root_labels) and len(set(root_labels)) == len(root_labels), f"{expected_id}: root identity")
    repeats = report.get("repeats")
    require(isinstance(repeats, list) and len(repeats) == 2, f"{expected_id}: exact-repeat count")
    require([item.get("repeat_index") for item in repeats] == [1, 2], f"{expected_id}: repeat index")
    require(len({item.get("nonce") for item in repeats}) == 2 and all(NONCE_RE.fullmatch(item.get("nonce", "")) for item in repeats), f"{expected_id}: repeat nonce")
    require(report.get("gates", {}).get("internal_exact_repeat") is True, f"{expected_id}: exact-repeat claim")
    require(repeat_payload_exact(repeats, report["engine"]), f"{expected_id}: exact-repeat payload drift")
    require(all(item.get("status") == "passed" and item.get("source_inventory_unchanged") is True for item in repeats), f"{expected_id}: runtime/source status")
    require(all(item.get("route") == ("public_root_sipi_com_run" if report["engine"] == "rust" else "pinned_agent_com_matlab_core_uninstrumented") for item in repeats), f"{expected_id}: route")
    expected_binding = {"case_index": SELECTED_CASE_INDEX, "port": SELECTED_PORT, "package_testcase_index": PACKAGE_TESTCASE_INDEX}
    for repeat in repeats:
        cases = repeat.get("cases")
        require(isinstance(cases, list) and len(cases) == len(CASE_INDICES), f"{expected_id}: selected case count")
        require([case.get("case_index") for case in cases] == list(CASE_INDICES), f"{expected_id}: selected case order")
        require(all(case.get("vector_binding") == expected_binding for case in cases), f"{expected_id}: case/port reuse or swap")
        sidecar = repeat.get("sidecar")
        require(isinstance(sidecar, dict), f"{expected_id}: diagnostic sidecar receipt")
        require(sidecar.get("selected_case_index") == SELECTED_CASE_INDEX and sidecar.get("package_testcase_index") == PACKAGE_TESTCASE_INDEX and sidecar.get("selected_port") == SELECTED_PORT and sidecar.get("case_to_port") == [expected_binding], f"{expected_id}: diagnostic sidecar binding")
        semantic = repeat.get("semantic_wall_clock_s")
        diagnostic = repeat.get("diagnostic_wall_clock_s")
        require(isinstance(semantic, (int, float)) and not isinstance(semantic, bool) and math.isfinite(float(semantic)) and semantic > 0.0, f"{expected_id}: semantic timing")
        require(isinstance(diagnostic, (int, float)) and not isinstance(diagnostic, bool) and math.isfinite(float(diagnostic)) and diagnostic > 0.0, f"{expected_id}: diagnostic timing")
        case_timing = repeat.get("case_wall_clock_s")
        require(isinstance(case_timing, list) and len(case_timing) == 1 and case_timing[0] == semantic, f"{expected_id}: semantic case timing split")
    performance = report.get("performance")
    require(isinstance(performance, dict) and performance.get("instrumented_trace_included") is False and performance.get("semantic_timing_source") == "un-instrumented_semantic_invocation_only" and performance.get("diagnostic_trace_timing_recorded") is True, f"{expected_id}: performance timing contract")
    if report["engine"] == "matlab":
        require(report.get("gates", {}).get("mat_bridge") is True, f"{expected_id}: MAT bridge claim")
        require(all(item.get("parameter_bridge", {}).get("passed") is True for item in repeats), f"{expected_id}: MAT bridge result")
    return root_labels


def _case_timing(report: dict[str, Any]) -> list[list[float] | None]:
    values = []
    for repeat in report["repeats"]:
        timing = repeat.get("case_wall_clock_s")
        if not isinstance(timing, list) or len(timing) != len(CASE_INDICES) or not all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(float(item)) and item > 0 for item in timing):
            values.append(None)
        else:
            values.append([float(item) for item in timing])
    return values


def _case_data(report: dict[str, Any]) -> list[dict[str, Any]]:
    cases = report["repeats"][0].get("cases")
    require(isinstance(cases, list) and len(cases) == len(CASE_INDICES), f"{report['run_id']}: case count")
    require([item.get("case_index") for item in cases] == list(CASE_INDICES), f"{report['run_id']}: case order")
    return cases


def aggregate_documents(reports: list[dict[str, Any]], report_digests: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return a blocked aggregate unless every v4 gate is mechanically closed."""
    require(len(reports) == len(RUN_IDS), "exactly four reports are required")
    ids = [report.get("run_id") for report in reports]
    require(set(ids) == RUN_IDS and len(ids) == len(set(ids)), "fixed replay id set")
    root_labels: list[str] = []
    for report in reports:
        root_labels.extend(_validate_runtime_report(report, report["run_id"]))
    require(len(root_labels) == len(set(root_labels)), "independent replay roots")
    nonces = [report["nonce"] for report in reports]
    require(len(nonces) == len(set(nonces)), "independent replay nonces")
    matlab = {report["run_id"]: report for report in reports if report["engine"] == "matlab"}
    rust = {report["run_id"]: report for report in reports if report["engine"] == "rust"}
    require(set(matlab) == {"matlab-01", "matlab-02"} and set(rust) == {"rust-01", "rust-02"}, "two reports per engine")
    blockers: set[str] = set()
    comparisons = []
    for index in (1, 2):
        matlab_report = matlab[f"matlab-0{index}"]
        rust_report = rust[f"rust-0{index}"]
        matlab_cases = _case_data(matlab_report)
        rust_cases = _case_data(rust_report)
        scalar = compare_scalar([case["metrics"] for case in matlab_cases], [case["metrics"] for case in rust_cases])
        vectors = []
        for case_index in CASE_INDICES:
            left = matlab_cases[case_index].get("vectors", [])
            right = rust_cases[case_index].get("vectors", [])
            vectors.append({"case_index": case_index, **compare_vectors(left, right)})
        pair_passed = scalar["passed"] and all(item["passed"] for item in vectors)
        comparisons.append({"pair": f"matlab-0{index}-rust-0{index}", "scalar": scalar, "vectors": vectors, "passed": pair_passed})
        if not scalar["passed"]:
            blockers.add(f"pair_{index}_scalar_surface_drift")
        if not all(item["passed"] for item in vectors):
            blockers.add(f"pair_{index}_vector_surface_drift")
    timing = {report["run_id"]: _case_timing(report) for report in reports}
    for index in (1, 2):
        matlab_time = timing[f"matlab-0{index}"]
        rust_time = timing[f"rust-0{index}"]
        for repeat_index, (matlab_repeat, rust_repeat) in enumerate(zip(matlab_time, rust_time), start=1):
            if not isinstance(matlab_repeat, list) or not isinstance(rust_repeat, list):
                blockers.add(f"pair_{index}_repeat_{repeat_index}_per_case_timing_missing")
            else:
                for case_index, (rust_seconds, matlab_seconds) in enumerate(zip(rust_repeat, matlab_repeat)):
                    if not rust_seconds < matlab_seconds:
                        blockers.add(f"pair_{index}_repeat_{repeat_index}_case_{case_index}_rust_not_faster")
    for report in reports:
        if report.get("status") != "passed":
            blockers.add(f"{report['run_id']}_runtime_status_{report.get('status')}")
        if report.get("engine") == "matlab" and report.get("gates", {}).get("mat_bridge") is not True:
            blockers.add(f"{report['run_id']}_mat_bridge")
    digest_map = report_digests or {report["run_id"]: {"sha256": _canonical_digest(report), "bytes": len(json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8"))} for report in reports}
    return {
        "schema": SCHEMA,
        "diagnostic_only": True,
        "formal_record": False,
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(blockers),
        "candidate": CANDIDATE_RECEIPT,
        "upstream": UPSTREAM_RECEIPT,
        "reports": digest_map,
        "gates": {
            "independent_replay_roots": len(root_labels) == len(set(root_labels)),
            "independent_replay_nonces": len(nonces) == len(set(nonces)),
            "internal_exact_repeat": all(report.get("gates", {}).get("internal_exact_repeat") is True for report in reports),
            "ordered_elementwise_vector_comparison": not any("vector_surface_drift" in blocker for blocker in blockers),
            "performance_each_case_rust_strictly_faster": not any("rust_not_faster" in blocker or "timing_missing" in blocker for blocker in blockers),
            "mat_bridge": all(report.get("engine") != "matlab" or report.get("gates", {}).get("mat_bridge") is True for report in reports),
        },
        "comparison": {"pairs": comparisons, "policy": "elementwise_no_alignment_or_transform"},
        "d3": {"status": "not_evaluated_configuration_disables_tdiln", "global_d3_enabled": True},
        "performance": {"instrumented_trace_included": False, "semantic_timing_source": "un-instrumented_semantic_invocation_only", "diagnostic_trace_timing_recorded": True, "per_case": timing},
        "claims": {"acceptance": False, "release": False, "vector_parity": not bool(blockers)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    require(len(args.report) == 4, "pass exactly four --report paths")
    require(not args.output.exists(), "aggregate output already exists")
    root = Path(__file__).resolve().parents[1]
    require(root not in args.output.resolve().parents and args.output.resolve() != root, "aggregate output must stay outside repository")
    reports = []
    digests = {}
    for path in args.report:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reports.append(payload)
        digests[payload["run_id"]] = {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
    aggregate = aggregate_documents(reports, digests)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aggregate, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": aggregate["status"], "blockers": aggregate["blockers"], "aggregate_sha256": sha256_file(args.output)}, sort_keys=True))
    return 0 if aggregate["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
