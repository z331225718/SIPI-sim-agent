"""Exact gate for one AS-05 ngspice scoped observation report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_as05_ngspice_bound as runner  # noqa: E402

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
TOP_KEYS = {"schema", "status", "scope", "run_id", "fresh_run_nonce", "candidate", "upstream", "runner", "toolchain", "build", "solver", "fixtures", "cases", "path_policy"}
SCOPE_KEYS = {"external_solver_not_verified", "numeric_parity", "parity_claim", "as05_row_closed", "release", "environment_injection_not_fully_excluded"}
IDENTITY_KEYS = {"role", "basename", "path_redacted", "file_sha256", "file_bytes", "version_exit_code", "version_output_sha256", "version_output_bytes", "timeout_seconds", "max_output_bytes"}
SOLVER_KEYS = IDENTITY_KEYS | {"caller_sha256", "pre_file_sha256", "post_file_sha256", "pre_file_bytes", "post_file_bytes", "pre_basename", "post_basename"}
BUILD_KEYS = {"exit_code", "stdout_bytes", "stdout_sha256", "stderr_bytes", "stderr_sha256", "binary_path_redacted", "binary_bytes", "binary_sha256", "offline", "locked", "target_dir_redacted", "rustc_env_identity", "wrapper_policy"}
FIXTURE_KEYS = {"id", "kind", "generated_by_runner", "path", "bytes", "sha256"}
CLI_KEYS = {"stdout_bytes", "stdout_sha256", "stderr_bytes", "stderr_sha256"}
PHYSICAL_KEYS = {"path", "bytes", "sha256"}
ARTIFACT_KEYS = PHYSICAL_KEYS
SUMMARY_KEYS = {"path", "bytes", "sha256", "ok", "backend", "external_runtime_sha256", "output_contract", "measurements", "waveform_rows", "artifacts"}
RUN_REPORT_KEYS = {"path", "bytes", "sha256", "status", "backend", "execute"}
WAVEFORM_KEYS = {"present", "path", "bytes", "sha256"}
CASE_KEYS = {"id", "kind", "returncode", "cli", "summary", "run_report", "waveform", "consumed_input"}
CONSUMED_INPUT_KEYS = {"path", "bytes", "sha256"}
CONTRACT_KEYS = {"normalizer", "requested", "returned", "result_kind", "verification", "caller_input_attestation"}
MEASUREMENT_KEYS = {"name", "value"}
PATH_POLICY = "path_free_report_create_new_scoped_external_observation_no_parity_no_release"
MEASURE_SOURCE_SHA256 = "cbb851db87c951e1d3a76cc99f6d1bb9fc31a3c4c20234d25507cd85d71695f4"
NORMALIZER_KEYS = {"upstream_path", "upstream_sha256"}
REQUESTED_KEYS = {"probes", "measures"}
RETURNED_KEYS = {"waveform_rows", "measurements"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(value: Any, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def no_absolute(value: Any) -> bool:
    if isinstance(value, dict):
        return all(no_absolute(item) for item in value.values())
    if isinstance(value, list):
        return all(no_absolute(item) for item in value)
    if not isinstance(value, str):
        return True
    normalized = value.replace("\\", "/")
    return not bool(re.search(r"(?:^[A-Za-z]:|^/|//)", normalized))

def relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value.replace("\\", "/")
    return not normalized.startswith("/") and not re.match(r"^[A-Za-z]:", normalized) and ".." not in normalized.split("/") and no_absolute(normalized)


def finite(value: Any) -> bool:
    if isinstance(value, dict):
        return all(finite(item) for item in value.values())
    if isinstance(value, list):
        return all(finite(item) for item in value)
    return not isinstance(value, float) or math.isfinite(value)


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def is_int(value: Any) -> bool:
    return type(value) is int


def is_number(value: Any) -> bool:
    return type(value) in (int, float)


def verify(document: dict[str, Any], *, candidate_commit: str, candidate_tree: str, candidate_archive_sha256: str, upstream_archive_sha256: str, solver_sha256: str, expected_runner_sha256: str, expected_report_sha256: str, report_path: Path) -> dict[str, Any]:
    blockers: list[str] = []
    if not HEX40.fullmatch(candidate_commit) or not HEX40.fullmatch(candidate_tree) or not valid_hash(candidate_archive_sha256) or not valid_hash(upstream_archive_sha256) or not valid_hash(solver_sha256) or not valid_hash(expected_runner_sha256) or not valid_hash(expected_report_sha256):
        blockers.append("hash argument shape")
    if not exact(document, TOP_KEYS):
        blockers.append("top-level keys")
    if document.get("schema") != "sipi.as-05-ngspice-scoped-observation.v2-prep" or document.get("status") != "scoped_external_runtime_observation_open":
        blockers.append("schema/status")
    if document.get("scope") != {"external_solver_not_verified": True, "numeric_parity": False, "parity_claim": False, "as05_row_closed": False, "release": False, "environment_injection_not_fully_excluded": True}:
        blockers.append("scope promotion")
    if document.get("path_policy") != PATH_POLICY:
        blockers.append("path policy")
    if not RUN_ID.fullmatch(str(document.get("run_id", ""))) or not valid_hash(document.get("fresh_run_nonce")):
        blockers.append("run identity")
    candidate = document.get("candidate")
    if not exact(candidate, {"commit", "tree", "archive_sha256"}) or candidate != {"commit": candidate_commit, "tree": candidate_tree, "archive_sha256": candidate_archive_sha256} or not HEX40.fullmatch(str(candidate.get("commit", ""))) or not HEX40.fullmatch(str(candidate.get("tree", ""))) or not valid_hash(candidate.get("archive_sha256")):
        blockers.append("candidate binding")
    upstream = document.get("upstream")
    if not exact(upstream, {"commit", "tree", "archive_sha256"}) or upstream != {"commit": runner.UPSTREAM_COMMIT, "tree": runner.UPSTREAM_TREE, "archive_sha256": upstream_archive_sha256} or not valid_hash(upstream.get("archive_sha256")):
        blockers.append("upstream binding")
    if not exact(document.get("runner"), {"path", "sha256"}) or document["runner"].get("path") != "tools/run_as05_ngspice_bound.py" or document["runner"].get("sha256") != expected_runner_sha256 or not valid_hash(document["runner"].get("sha256")):
        blockers.append("runner binding")
    toolchain = document.get("toolchain")
    if not exact(toolchain, {"git", "cargo", "rustc", "python"}):
        blockers.append("toolchain keys")
    else:
        for role, identity in toolchain.items():
            if (not exact(identity, IDENTITY_KEYS) or identity.get("role") != role
                    or not isinstance(identity.get("basename"), str) or not identity.get("basename")
                    or "/" in identity["basename"] or "\\" in identity["basename"] or ":" in identity["basename"]
                    or identity.get("path_redacted") is not True or not is_int(identity.get("version_exit_code"))
                    or identity.get("version_exit_code") != 0 or not is_int(identity.get("timeout_seconds"))
                    or identity.get("timeout_seconds") != runner.VERSION_TIMEOUT_SECONDS
                    or not is_int(identity.get("max_output_bytes")) or identity.get("max_output_bytes") != runner.MAX_VERSION_BYTES
                    or not valid_hash(identity.get("file_sha256")) or not valid_hash(identity.get("version_output_sha256"))
                    or not is_int(identity.get("file_bytes")) or identity.get("file_bytes", 0) <= 0 or identity.get("file_bytes", 0) > runner.MAX_FILE_BYTES
                    or not is_int(identity.get("version_output_bytes")) or identity.get("version_output_bytes", 0) < 0 or identity.get("version_output_bytes", 0) > runner.MAX_VERSION_BYTES):
                blockers.append(f"toolchain identity:{role}")
    build = document.get("build")
    if (not exact(build, BUILD_KEYS) or not is_int(build.get("exit_code")) or build.get("exit_code") != 0
            or build.get("offline") is not True or build.get("locked") is not True
            or build.get("target_dir_redacted") is not True or build.get("binary_path_redacted") is not True
            or build.get("wrapper_policy") != "RUSTC_WRAPPER_RUSTC_WORKSPACE_WRAPPER_CARGO_BUILD_RUSTC_WRAPPER_cleared"
            or not valid_hash(build.get("binary_sha256")) or not valid_hash(build.get("rustc_env_identity"))
            or build.get("rustc_env_identity") != document.get("toolchain", {}).get("rustc", {}).get("file_sha256")
            or not valid_hash(build.get("stdout_sha256")) or not valid_hash(build.get("stderr_sha256"))
            or not is_int(build.get("stdout_bytes")) or build.get("stdout_bytes", -1) < 0 or build.get("stdout_bytes", 0) > runner.MAX_ARCHIVE_BYTES
            or not is_int(build.get("stderr_bytes")) or build.get("stderr_bytes", -1) < 0 or build.get("stderr_bytes", 0) > runner.MAX_ARCHIVE_BYTES
            or build.get("stdout_bytes", 0) + build.get("stderr_bytes", 0) > runner.MAX_ARCHIVE_BYTES
            or not is_int(build.get("binary_bytes")) or build.get("binary_bytes", 0) <= 0 or build.get("binary_bytes", 0) > runner.MAX_FILE_BYTES):
        blockers.append("build binding")
    solver = document.get("solver")
    if (not exact(solver, SOLVER_KEYS) or solver.get("role") != "ngspice" or solver.get("path_redacted") is not True
            or not isinstance(solver.get("basename"), str) or not solver.get("basename") or "/" in solver["basename"] or "\\" in solver["basename"] or ":" in solver["basename"]
            or solver.get("caller_sha256") != solver_sha256 or not valid_hash(solver.get("caller_sha256"))
            or solver.get("file_sha256") != solver_sha256 or not valid_hash(solver.get("file_sha256"))
            or solver.get("pre_file_sha256") != solver_sha256 or not valid_hash(solver.get("pre_file_sha256"))
            or solver.get("post_file_sha256") != solver_sha256 or not valid_hash(solver.get("post_file_sha256"))
            or solver.get("pre_file_bytes") != solver.get("file_bytes") or solver.get("post_file_bytes") != solver.get("file_bytes")
            or not is_int(solver.get("file_bytes")) or solver.get("file_bytes", 0) <= 0 or solver.get("file_bytes", 0) > runner.MAX_FILE_BYTES
            or not is_int(solver.get("pre_file_bytes")) or solver.get("pre_file_bytes", 0) <= 0 or solver.get("pre_file_bytes", 0) > runner.MAX_FILE_BYTES
            or not is_int(solver.get("post_file_bytes")) or solver.get("post_file_bytes", 0) <= 0 or solver.get("post_file_bytes", 0) > runner.MAX_FILE_BYTES
            or solver.get("pre_basename") != solver.get("basename") or solver.get("post_basename") != solver.get("basename")
            or not is_int(solver.get("version_exit_code")) or solver.get("version_exit_code") != 0
            or not is_int(solver.get("timeout_seconds")) or solver.get("timeout_seconds") != runner.VERSION_TIMEOUT_SECONDS
            or not is_int(solver.get("max_output_bytes")) or solver.get("max_output_bytes") != runner.MAX_VERSION_BYTES
            or not is_int(solver.get("version_output_bytes")) or solver.get("version_output_bytes", 0) < 0 or solver.get("version_output_bytes", 0) > runner.MAX_VERSION_BYTES
            or not valid_hash(solver.get("version_output_sha256"))):
        blockers.append("solver binding")
    expected_fixtures = [{"id": item[0], "kind": item[1], "generated_by_runner": runner.FIXTURE_GENERATOR, "path": f"fixtures/{item[0]}.sp", "bytes": len(item[2].encode("ascii")), "sha256": hashlib.sha256(item[2].encode("ascii")).hexdigest()} for item in runner.FIXTURES]
    fixtures = document.get("fixtures")
    fixture_list = fixtures if isinstance(fixtures, list) else []
    if not isinstance(fixtures, list) or fixtures != expected_fixtures or any(not exact(item, FIXTURE_KEYS) or not relative(item.get("path")) or not is_int(item.get("bytes")) or item.get("bytes", 0) <= 0 or item.get("bytes", 0) > runner.MAX_FILE_BYTES for item in fixture_list):
        blockers.append("fixture exact binding")
    cases = document.get("cases")
    expected_ids = [item[0] for item in runner.FIXTURES]
    valid_case_container = isinstance(cases, list) and all(isinstance(item, dict) for item in cases) and [item.get("id") for item in cases] == expected_ids and all(exact(item, CASE_KEYS) for item in cases)
    if not valid_case_container:
        blockers.append("case ordering/keys")
    if isinstance(cases, list) and any(not isinstance(item, dict) for item in cases):
        blockers.append("case non-dict")
    if valid_case_container:
        for case in cases:
            if not is_int(case.get("returncode")) or case.get("returncode") != 0 or not exact(case.get("cli"), CLI_KEYS) or not exact(case.get("summary"), SUMMARY_KEYS) or not exact(case.get("run_report"), RUN_REPORT_KEYS) or not exact(case.get("waveform"), WAVEFORM_KEYS):
                blockers.append(f"case shape:{case.get('id')}")
                continue
            expected_kind = {"uppercase_tran": "uppercase_tran_v1", "measure_only": "measure_only_v1"}[case["id"]]
            if case.get("kind") != expected_kind:
                blockers.append(f"case kind:{case.get('id')}")
            consumed_input = case.get("consumed_input")
            expected_input = next((item for item in fixture_list if isinstance(item, dict) and item.get("id") == case["id"]), None)
            if (expected_input is None or not exact(consumed_input, CONSUMED_INPUT_KEYS)
                    or consumed_input.get("path") != expected_input.get("path")
                    or consumed_input.get("bytes") != expected_input.get("bytes")
                    or consumed_input.get("sha256") != expected_input.get("sha256")
                    or not is_int(consumed_input.get("bytes")) or consumed_input.get("bytes", 0) <= 0
                    or consumed_input.get("bytes", 0) > runner.MAX_FILE_BYTES):
                blockers.append(f"consumed input binding:{case.get('id')}")
            if (any(not is_int(case["cli"].get(key)) or case["cli"].get(key, -1) < 0 or case["cli"].get(key, 0) > runner.MAX_VERSION_BYTES for key in ("stdout_bytes", "stderr_bytes"))
                    or case["cli"].get("stdout_bytes", 0) + case["cli"].get("stderr_bytes", 0) > runner.MAX_VERSION_BYTES
                    or any(not valid_hash(case["cli"].get(key)) for key in ("stdout_sha256", "stderr_sha256"))):
                blockers.append(f"cli physical binding:{case.get('id')}")
            summary = case["summary"]
            contract = summary.get("output_contract")
            if summary.get("ok") is not True or summary.get("backend") != "ngspice" or summary.get("external_runtime_sha256") != solver_sha256 or not exact(contract, CONTRACT_KEYS):
                blockers.append(f"summary contract:{case.get('id')}")
                continue
            normalizer = contract.get("normalizer")
            requested = contract.get("requested")
            returned = contract.get("returned")
            if (not exact(normalizer, NORMALIZER_KEYS) or normalizer.get("upstream_sha256") != MEASURE_SOURCE_SHA256
                    or not exact(requested, REQUESTED_KEYS) or not exact(returned, RETURNED_KEYS)
                    or contract.get("result_kind") != "ngspice_print_table_observation"
                    or contract.get("verification") != "external_solver_not_verified"
                    or contract.get("caller_input_attestation") != "caller_input_unattested"):
                blockers.append(f"summary contract:{case.get('id')}")
                continue
            expected_requested = {
                "uppercase_tran": {"probes": ["V(OUT)"], "measures": [{"analysis": "tran", "name": "M_RMS", "operation": "find", "target": "V(OUT)", "raw": ".MEASURE TRAN M_RMS FIND V(OUT) AT=0"}]},
                "measure_only": {"probes": [], "measures": [{"analysis": "tran", "name": "M_ONLY", "operation": "find", "target": "V(OUT)", "raw": ".MEASURE TRAN M_ONLY FIND V(OUT) AT=0"}]},
            }[case["id"]]
            if contract.get("requested") != expected_requested:
                blockers.append(f"fixture request contract:{case.get('id')}")
            expected_measurement_name = {"uppercase_tran": "m_rms", "measure_only": "m_only"}[case["id"]]
            measurements = summary.get("measurements")
            if (not isinstance(measurements, list) or len(measurements) != 1
                    or not exact(measurements[0], MEASUREMENT_KEYS)
                    or measurements[0].get("name") != expected_measurement_name
                    or not is_number(measurements[0].get("value"))
                    or not math.isfinite(measurements[0]["value"])):
                blockers.append(f"measurement schema:{case.get('id')}")
            if (not is_int(returned.get("waveform_rows")) or returned.get("waveform_rows", -1) < 0
                    or not is_int(summary.get("waveform_rows")) or summary.get("waveform_rows", -1) < 0
                    or returned.get("waveform_rows") != summary.get("waveform_rows")
                    or returned.get("measurements") != measurements):
                blockers.append(f"returned contract binding:{case.get('id')}")
            artifacts = summary.get("artifacts")
            if (not isinstance(artifacts, list)
                    or len({item.get("path") for item in artifacts if isinstance(item, dict)}) != len(artifacts)
                    or any(not isinstance(item, dict) or not exact(item, ARTIFACT_KEYS) or not relative(item.get("path"))
                    or not valid_hash(item.get("sha256")) or not is_int(item.get("bytes"))
                           or item.get("bytes", -1) < 0
                    or item.get("bytes", 0) > runner.MAX_FILE_BYTES
                    or (item.get("path") in {"case", "waveform.csv"} and item.get("bytes", 0) <= 0)
                           for item in artifacts)):
                blockers.append(f"artifact contract:{case.get('id')}")
            else:
                expected_artifacts = {"case", "stdout.log", "stderr.log"}
                if case["waveform"].get("present"):
                    expected_artifacts.add("waveform.csv")
                if {item.get("path") for item in artifacts} != expected_artifacts:
                    blockers.append(f"artifact set:{case.get('id')}")
                waveform_artifacts = [item for item in artifacts if item.get("path") == "waveform.csv"]
                if case["waveform"].get("present") and (len(waveform_artifacts) != 1 or waveform_artifacts[0].get("sha256") != case["waveform"].get("sha256") or waveform_artifacts[0].get("bytes") != case["waveform"].get("bytes")):
                    blockers.append(f"waveform artifact physical binding:{case.get('id')}")
            if summary.get("path") != f"{case['id']}/run_summary.json" or not relative(summary.get("path")) or not valid_hash(summary.get("sha256")) or not is_int(summary.get("bytes")) or summary.get("bytes", 0) <= 0 or summary.get("bytes", 0) > runner.MAX_REPORT_BYTES or case["run_report"].get("path") != f"{case['id']}/run_report.json" or not relative(case["run_report"].get("path")) or not valid_hash(case["run_report"].get("sha256")) or not is_int(case["run_report"].get("bytes")) or case["run_report"].get("bytes", 0) <= 0 or case["run_report"].get("bytes", 0) > runner.MAX_REPORT_BYTES:
                blockers.append(f"physical report binding:{case.get('id')}")
            if case["run_report"].get("backend") != "ngspice" or case["run_report"].get("execute") is not True or case["run_report"].get("status") != "compatible":
                blockers.append(f"run report contract:{case.get('id')}")
            if case["id"] == "uppercase_tran" and (case["waveform"].get("present") is not True or not is_int(case["summary"].get("waveform_rows")) or case["summary"].get("waveform_rows", 0) <= 0 or case["summary"].get("waveform_rows", 0) > case["waveform"].get("bytes", 0) or case["summary"].get("waveform_rows", 0) > runner.MAX_FILE_BYTES):
                blockers.append("uppercase waveform missing")
            if not isinstance(case["summary"].get("measurements"), list) or not case["summary"]["measurements"]:
                blockers.append(f"nontrivial measurement missing:{case.get('id')}")
            if contract.get("normalizer", {}).get("upstream_path") != "src/agent_spice/hspice/measure.py::normalize_outputs":
                blockers.append(f"normalizer identity:{case.get('id')}")
            if case["id"] == "measure_only" and (case["waveform"].get("present") is not False or case["summary"].get("waveform_rows") != 0):
                blockers.append("measure-only waveform present")
            waveform = case["waveform"]
            if waveform.get("present"):
                if not relative(waveform.get("path")) or waveform.get("path") != "waveform.csv" or not valid_hash(waveform.get("sha256")) or not is_int(waveform.get("bytes")) or waveform.get("bytes", 0) <= 0 or waveform.get("bytes", 0) > runner.MAX_FILE_BYTES:
                    blockers.append(f"waveform physical binding:{case.get('id')}")
            elif waveform.get("path") is not None or not is_int(waveform.get("bytes")) or waveform.get("bytes") != 0 or waveform.get("sha256") is not None:
                blockers.append(f"waveform absent shape:{case.get('id')}")
    if not no_absolute(document) or not finite(document):
        blockers.append("path or finite-value policy")
    if not report_path.is_file() or sha(report_path) != expected_report_sha256:
        blockers.append("report self hash")
    return {"valid": not blockers, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--candidate-archive-sha256", required=True)
    parser.add_argument("--upstream-archive-sha256", required=True)
    parser.add_argument("--ngspice-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--expected-report-sha256", required=True)
    args = parser.parse_args()
    path = args.report if args.report.is_absolute() else ROOT / args.report
    result = verify(json.loads(path.read_text(encoding="utf-8")), candidate_commit=args.candidate_commit, candidate_tree=args.candidate_tree, candidate_archive_sha256=args.candidate_archive_sha256, upstream_archive_sha256=args.upstream_archive_sha256, solver_sha256=args.ngspice_sha256, expected_runner_sha256=args.expected_runner_sha256, expected_report_sha256=args.expected_report_sha256, report_path=path)
    print("valid" if result["valid"] else "blocked")
    for blocker in result["blockers"]:
        print(f"- {blocker}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
