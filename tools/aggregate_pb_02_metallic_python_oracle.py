"""Deterministically aggregate the two PB-02 prep-policy reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "docs/baselines/pb-02-metallic-python-oracle-corpus.v1.json"
EXPECTED_CASES = ["metallic-ctle-ordinary-3ghz-10ghz", "metallic-ctle-near-integral-3ghz"]
EXPECTED_CANDIDATE = {
    "commit": "dc82489d109f27b70940a5f1037cb08d3c10a8b6",
    "tree": "6311d5a0e88cd008e22ab9dcc0e7c18f57120ed3",
    "archive_sha256": "dcf9e38aaf0980c40a6c7640e5c229ac851a11e7c287d4bde386b21b1e9c5b00",
}
EXPECTED_SOURCE_MODE = "git_archive_at_candidate_prep_commit_plus_content_addressed_input_corpus_and_harness_snapshot"
EXPECTED_UPSTREAM = {
    "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
    "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
    "archive_sha256": "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25",
}
EXPECTED_CORPUS = "docs/baselines/pb-02-metallic-python-oracle-corpus.v1.json"
EXPECTED_CORPUS_SHA256 = "e14a440945de59c14dbd0438a7d2e6e8785d1dc201f1e3b4c7fecdc691561d5c"
EXPECTED_FIXTURE = "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml"
EXPECTED_FIXTURE_SHA256 = "2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f"
EXPECTED_HARNESS_PATHS = {
    "runner": "tools/run_pb_03_python_oracle_matrix.py",
    "python_oracle": "tools/pb_02_metallic_python_oracle.py",
    "wrapper": "tools/run_pb_02_metallic_python_oracle.py",
}
EXPECTED_HARNESS_SHA256 = {
    "runner": "31e5dddd19f608497cfb34a95b5fb0b223b51d790db09b44207485dc1223b5f3",
    "python_oracle": "9c110467d7d97039ba1d425b4a4aa100e452da8e823a599bd6fbb26911804fea",
    "wrapper": "45d2f5efafdf9e00a7f06c5ca157bc641da2ea02d01f3ccd175060e5e9ed4732",
}
EXPECTED_FIELDS = [
    "channel_impulse_v_per_v", "channel_output_v", "legacy_channel_frequency_hz", "legacy_channel_raw_re", "legacy_channel_raw_im",
    "legacy_channel_terminated_re", "legacy_channel_terminated_im", "legacy_channel_trimmed_re", "legacy_channel_trimmed_im",
    "rx_filter_impulse_v_per_v", "legacy_stage_ctle_re", "legacy_stage_ctle_im", "legacy_stage_ctle_out_re", "legacy_stage_ctle_out_im",
    "ctle_output_v", "rx_output_v", "dfe_output_v",
]
HEX64 = set("0123456789abcdef")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    value = path.resolve().relative_to(ROOT.resolve()).as_posix()
    if value.startswith("/") or ".." in Path(value).parts:
        raise ValueError("report path is not repository-relative")
    return value


def _identity(reports: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [report.get(key) for report in reports]
    if len(values) != 2 or values[0] != values[1] or not isinstance(values[0], dict):
        raise ValueError(f"{key} differs across fresh reports")
    return values[0]


def _source_gate(report: dict[str, Any]) -> dict[str, Any]:
    candidate = report.get("candidate")
    upstream = report.get("upstream")
    corpus = report.get("corpus")
    fixture = report.get("fixture")
    harness = report.get("harness")
    if candidate != EXPECTED_CANDIDATE or upstream != EXPECTED_UPSTREAM:
        raise ValueError("candidate or pinned upstream identity drift")
    if report.get("source_mode") != EXPECTED_SOURCE_MODE:
        raise ValueError("source mode drift")
    if not isinstance(corpus, dict) or corpus.get("path") != EXPECTED_CORPUS or corpus.get("sha256") != EXPECTED_CORPUS_SHA256:
        raise ValueError("corpus binding drift")
    if not isinstance(fixture, dict) or fixture.get("path") != EXPECTED_FIXTURE or fixture.get("sha256") != EXPECTED_FIXTURE_SHA256 or fixture.get("archive_present") is not True or fixture.get("source") != "candidate_archive":
        raise ValueError("fixture binding drift")
    if not isinstance(harness, dict):
        raise ValueError("harness binding is missing")
    if set(harness) != set(EXPECTED_HARNESS_PATHS):
        raise ValueError("harness role set drift")
    for role, path in EXPECTED_HARNESS_PATHS.items():
        item = harness.get(role)
        if not isinstance(item, dict) or item.get("path") != path or item.get("sha256") != EXPECTED_HARNESS_SHA256[role]:
            raise ValueError(f"harness binding drift: {role}")
    return {"candidate": candidate, "upstream": upstream, "source_mode": report["source_mode"], "corpus": corpus, "fixture": fixture, "harness": harness}


def _toolchain_gate(report: dict[str, Any]) -> dict[str, Any]:
    value = report.get("toolchain")
    if not isinstance(value, dict):
        raise ValueError("toolchain is missing")
    if set(value) != {"timeout_seconds", "cargo", "rustc", "uv", "python", "child_python", "host_python"}:
        raise ValueError("toolchain role set drift")
    def strip_io(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: strip_io(value) for key, value in item.items() if key not in {"stdout_sha256", "stderr_sha256", "stdout_json", "stderr_json"}}
        if isinstance(item, list):
            return [strip_io(value) for value in item]
        return item
    return strip_io(value)


def _toolchain_contract(value: dict[str, Any]) -> None:
    for role in ("cargo", "rustc", "uv", "python"):
        item = value.get(role)
        if not isinstance(item, dict) or set(item) != {"role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"}:
            raise ValueError("toolchain role key drift")
        if item.get("role") != role or item.get("path_redacted") is not True or item.get("version_exit_code") != 0:
            raise ValueError("toolchain role identity drift")
        if not all(isinstance(item.get(key), str) and len(item[key]) == 64 for key in ("file_sha256", "version_output_sha256")):
            raise ValueError("toolchain role hash drift")
    child = value.get("child_python")
    if not isinstance(child, dict) or set(child) != {"command", "identity", "process"} or not isinstance(child.get("identity"), dict) or not isinstance(child.get("process"), dict) or child["process"].get("exit_code") != 0:
        raise ValueError("child Python contract drift")
    identity = child["identity"]
    if set(identity) != {"python", "numpy", "scipy"}:
        raise ValueError("child Python identity key drift")
    py = identity["python"]
    if not isinstance(py, dict) or set(py) != {"executable", "file_sha256", "implementation", "version", "path_redacted"} or py.get("path_redacted") is not True:
        raise ValueError("child Python executable identity drift")
    if not isinstance(py.get("file_sha256"), str) or len(py["file_sha256"]) != 64:
        raise ValueError("child Python file hash drift")
    for key, expected in (("numpy", {"module", "version", "core_module"}), ("scipy", {"module", "version"})):
        if not isinstance(identity[key], dict) or set(identity[key]) != expected:
            raise ValueError("numeric module identity drift")
    host = value.get("host_python")
    if not isinstance(host, dict) or set(host) != {"executable", "file_sha256", "path_redacted", "source"} or host.get("path_redacted") is not True:
        raise ValueError("host Python contract drift")
    if not isinstance(host.get("file_sha256"), str) or len(host["file_sha256"]) != 64:
        raise ValueError("host Python file hash drift")


def _build_gate(report: dict[str, Any]) -> dict[str, Any]:
    build = report.get("build")
    if not isinstance(build, dict) or not isinstance(build.get("binary_custody"), dict):
        raise ValueError("binary custody is missing")
    custody = build["binary_custody"]
    if build.get("binary_sha256") != custody.get("raw_sha256"):
        raise ValueError("binary raw custody mismatch")
    if build.get("environment_policy") != {
        "rustc_wrapper_cleared": True,
        "rustc_workspace_wrapper_cleared": True,
        "cargo_build_rustc_wrapper_cleared": True,
    }:
        raise ValueError("build wrapper environment policy drift")
    def canonical_shape(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: canonical_shape(value) for key, value in item.items() if key != "raw_hex"}
        if isinstance(item, list):
            return [canonical_shape(value) for value in item]
        return item
    return {
        "exit_code": build.get("exit_code"),
        "environment_policy": build.get("environment_policy"),
        "canonical_sha256": custody.get("canonical_sha256"),
        "format": custody.get("format"),
        "machine": custody.get("machine"),
        "profile": custody.get("profile"),
        "normalization": canonical_shape(custody.get("normalization")),
    }


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _summary(value: Any) -> bool:
    sha = value.get("f64_sha256") if isinstance(value, dict) else None
    return isinstance(value, dict) and set(value) == {"dtype", "shape", "count", "f64_sha256"} and value.get("dtype") == "float64" and isinstance(value.get("shape"), list) and isinstance(value.get("count"), int) and isinstance(sha, str) and len(sha) == 64 and set(sha) <= HEX64


def _payload_gate(report: dict[str, Any]) -> list[dict[str, Any]]:
    cases = report.get("cases")
    if not isinstance(cases, list) or [case.get("id") for case in cases] != EXPECTED_CASES:
        raise ValueError("case order drift")
    ordinary, near = cases
    if report.get("status") != "blocked":
        raise ValueError("overall status policy failed")
    for case in cases:
        candidate = case.get("candidate", {})
        oracle = case.get("oracle", {})
        if candidate.get("schema") != "pybert.native-cli-result.v1" or oracle.get("schema") != "pybert.python-oracle-result.v1" or oracle.get("backend") != "python" or oracle.get("source_command") != "PythonSimulationBackend":
            raise ValueError("candidate/oracle self-comparison or schema drift")
    if ordinary.get("status") != "passed" or ordinary.get("blockers") != [] or near.get("status") != "blocked":
        raise ValueError("case status policy failed")
    fields = ordinary.get("payload", {}).get("fields", [])
    if ordinary.get("candidate_process", {}).get("exit_code") != 0 or ordinary.get("oracle_process", {}).get("exit_code") != 0:
        raise ValueError("ordinary process policy failed")
    if ordinary.get("payload", {}).get("compared_field_count") != 17 or ordinary.get("payload", {}).get("equal") is not True:
        raise ValueError("ordinary payload policy failed")
    if len(fields) != 17 or [field.get("name") for field in fields] != EXPECTED_FIELDS or any(field.get("passed") is not True for field in fields):
        raise ValueError("ordinary field gate failed")
    for field in fields:
        if set(field) != {"name", "candidate", "oracle", "max_abs", "scale", "tolerance", "passed"} or not _summary(field["candidate"]) or not _summary(field["oracle"]):
            raise ValueError("ordinary payload summary schema drift")
        if not all(_finite(field[key]) for key in ("max_abs", "scale", "tolerance")):
            raise ValueError("ordinary payload metric is not finite")
    diagnostics = near.get("oracle", {}).get("diagnostics", {})
    if near.get("candidate_process", {}).get("exit_code") != 0 or near.get("oracle_process", {}).get("exit_code") != 1 or near.get("payload", {}).get("compared_field_count") != 0 or near.get("payload", {}).get("equal") is not False or near.get("payload", {}).get("fields") != [] or near.get("blockers") != ["pinned_channel_cubic_interp1d_two_point_boundary"]:
        raise ValueError("near-integral process policy failed")
    if diagnostics.get("failure_code") != "pinned_channel_cubic_interp1d_two_point_boundary" or diagnostics.get("failure_stage") != "channel":
        raise ValueError("near-integral blocker policy failed")
    return fields


def aggregate(report_paths: list[Path], output: Path) -> dict[str, Any]:
    if len(report_paths) != 2:
        raise ValueError("exactly two fresh reports are required")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in report_paths]
    if any(report.get("schema") != "sipi.pb-02-metallic-python-oracle-replay.v1" for report in reports):
        raise ValueError("report schema mismatch")
    if any(report.get("candidate") != EXPECTED_CANDIDATE for report in reports):
        raise ValueError("candidate prep identity mismatch")
    if any(report.get("source_mode") != EXPECTED_SOURCE_MODE for report in reports):
        raise ValueError("source mode mismatch")
    expected_claims = {
        "independent_python_payload_oracle": True,
        "ordinary_payload_parity": True,
        "near_integral_external_blocked": True,
        "near_integral_counted_as_parity": False,
        "global_branch_parity": False,
        "promotion": False,
    }
    if any(report.get("claims") != expected_claims for report in reports):
        raise ValueError("claims are not policy-proven")
    case_ids = [case.get("id") for case in reports[0].get("cases", [])]
    if case_ids != EXPECTED_CASES or [case.get("id") for case in reports[1].get("cases", [])] != EXPECTED_CASES:
        raise ValueError("case ids are not the locked corpus order")
    candidate = _identity(reports, "candidate")
    upstream = _identity(reports, "upstream")
    source_gate = _source_gate(reports[0])
    if any(_source_gate(report) != source_gate for report in reports[1:]):
        raise ValueError("source, fixture, corpus, or harness differs across reports")
    toolchain = _toolchain_gate(reports[0])
    _toolchain_contract(reports[0]["toolchain"])
    if any(_toolchain_gate(report) != toolchain for report in reports[1:]):
        raise ValueError("toolchain or child Python identity differs across reports")
    for report in reports[1:]:
        _toolchain_contract(report["toolchain"])
    build = _build_gate(reports[0])
    if any(_build_gate(report) != build for report in reports[1:]):
        raise ValueError("canonical PE custody differs across reports")
    payload = _payload_gate(reports[0])
    if _payload_gate(reports[1]) != payload:
        raise ValueError("payload gate differs across reports")
    entries = [
        {
            "path": relative(path),
            "sha256": digest(path),
            "run_id": report.get("run_id"),
            "fresh_run_nonce": report.get("fresh_run_nonce"),
        }
        for path, report in zip(report_paths, reports)
    ]
    if len({entry["path"] for entry in entries}) != 2 or len({entry["sha256"] for entry in entries}) != 2:
        raise ValueError("fresh report path or full SHA is duplicated")
    if len({entry["run_id"] for entry in entries}) != 2 or len({entry["fresh_run_nonce"] for entry in entries}) != 2:
        raise ValueError("fresh report run_id or nonce is duplicated")
    result = {
        "schema": "sipi.pb-02-metallic-python-oracle-aggregate.v2-prep",
        "version": 2,
        "status": "blocked_near_integral_external",
        "candidate": candidate,
        "upstream": upstream,
        "toolchain": toolchain,
        "build": build,
        "source_gate": source_gate,
        "payload": {"ordinary_field_count": 17, "ordinary_all_passed": True, "near_integral_counted_as_parity": False},
        "reports": entries,
        "case_ids": EXPECTED_CASES,
        "claims": {
            "independent_python_payload_oracle": True,
            "ordinary_payload_parity": True,
            "near_integral_external_blocked": True,
            "near_integral_counted_as_parity": False,
            "global_branch_parity": False,
            "promotion": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs=2, type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    aggregate(args.reports, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
