"""Fail-closed verifier for COM clean-archive immutable v2 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


HEX64 = re.compile(r"^[0-9a-f]{64}$")
ABSOLUTE = re.compile(r"(?:^[A-Za-z]:[\\/])|(?:^/)|(?:\\\\)")


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_absolute_path(value: object) -> bool:
    if isinstance(value, dict):
        return any(has_absolute_path(key) or has_absolute_path(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_absolute_path(item) for item in value)
    return isinstance(value, str) and bool(ABSOLUTE.search(value))


def verify_tool(value: object, role: str) -> None:
    require(isinstance(value, dict), f"{role} tool identity missing")
    require(value.get("role") == role, f"{role} role drift")
    executable = value.get("executable")
    require(isinstance(executable, str) and executable.lower() == f"{role}.exe", f"{role} basename drift")
    require(not has_absolute_path(executable), f"{role} path leaked")
    require(HEX64.fullmatch(value.get("file_sha256", "")), f"{role} file hash drift")
    require(HEX64.fullmatch(value.get("version_output_sha256", "")), f"{role} version hash drift")
    require(value.get("version_exit_code") == 0, f"{role} version failed")
    require(value.get("path_redacted") is True, f"{role} path redaction drift")
    require(value.get("timeout_seconds") == 30, f"{role} timeout drift")
    require(value.get("timed_out") is False, f"{role} timed out")


def verify_build(build: object, candidate: dict[str, Any], report_candidate: dict[str, Any]) -> None:
    require(isinstance(build, dict), "build provenance missing")
    require(build.get("returncode") == 0 and build.get("timed_out") is False, "build failed")
    require(build.get("timeout_seconds") == 300, "build timeout drift")
    require(build.get("rustc_wrapper_cleared") is True, "RUSTC_WRAPPER was not cleared")
    require(build.get("source_mode") == "candidate_git_archive_at_immutable_commit", "build source mode drift")
    require(build.get("source_commit") == candidate["commit"], "build source commit drift")
    require(build.get("source_tree") == candidate["tree"], "build source tree drift")
    require(build.get("archive_sha256") == candidate["archive_sha256"], "build archive drift")
    for field in ("stdout_sha256", "stderr_sha256"):
        require(HEX64.fullmatch(build.get(field, "")), f"build {field} drift")
    binary = build.get("binary", {})
    require(isinstance(binary, dict), "built binary identity missing")
    path = binary.get("path", "")
    require(isinstance(path, str) and not has_absolute_path(path), "binary path leak")
    require(path == candidate["binary"], "binary relative path drift")
    require(binary.get("sha256") == report_candidate["binary_sha256"], "built binary hash drift")
    require(binary.get("bytes") == report_candidate["binary_bytes"], "built binary size drift")


def verify(manifest_path: Path) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(document, dict), "manifest must be a mapping")
    scope = document.get("scope", {})
    mode = scope.get("work_item")
    require(mode in ("COM-02", "COM-04"), "work item drift")
    mode_key = mode.lower()
    require(document.get("schema") == f"sipi.{mode_key}.direct-port.v2", "schema drift")
    require(document.get("status") == "bound_clean_archive_observation_open", "status overclaim")
    audit_path = root / document["audit"]
    require(sha256(audit_path) == document.get("audit_sha256"), "audit hash drift")
    candidate = document.get("candidate", {})
    require(candidate.get("commit") == "64b783f66d7e986d0975be5ac3946b453b15c4ed", "candidate commit drift")
    require(candidate.get("tree") == "0e11721f2bb5b564002820cc7a5aaab45e30ba3b", "candidate tree drift")
    require(candidate.get("materialization") == "git archive; no working-tree overlay", "materialization drift")
    require(HEX64.fullmatch(candidate.get("archive_sha256", "")), "candidate archive hash drift")
    require(isinstance(candidate.get("binary_sha256_by_run"), list) and len(candidate["binary_sha256_by_run"]) == 2, "candidate binary hash set drift")
    require(all(HEX64.fullmatch(value) for value in candidate["binary_sha256_by_run"]), "candidate binary hash drift")
    require(not has_absolute_path(candidate), "absolute candidate path leaked")
    upstream = document.get("upstream", {})
    require(upstream == {
        "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
        "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
        "declared_license": "MIT",
        "source_map": upstream.get("source_map"),
        "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf",
        "materialization": "git archive at immutable commit metadata-only",
        "runtime_executed": False,
    }, "upstream identity/materialization drift")
    contract = document.get("contract", {})
    require(contract.get("s_parameter_fit") == "forbidden", "fit policy drift")
    require(contract.get("custody") == "reject_equal_ancestor_descendant_symlink_hardlink_before_artifact_mutation", "custody policy drift")
    oracle = document.get("oracle", {})
    require(oracle.get("fresh_runs") == 2 and oracle.get("scenario_count") == 10, "oracle count drift")
    expected = document.get("execution_binding", {})
    require(HEX64.fullmatch(expected.get("runner_sha256", "")), "runner hash missing")
    require(HEX64.fullmatch(expected.get("helper_sha256", "")), "helper hash missing")
    require(HEX64.fullmatch(expected.get("v2_wrapper_sha256", "")), "wrapper hash missing")
    require(HEX64.fullmatch(expected.get("aggregate_runner_sha256", "")), "aggregate runner hash missing")
    require(HEX64.fullmatch(expected.get("contract_test_runner_sha256", "")), "contract runner hash missing")
    require(HEX64.fullmatch(expected.get("fixture_corpus_sha256", "")), "fixture hash missing")
    require(expected.get("input_count") == 22, "fixture input count drift")
    require(HEX64.fullmatch(expected.get("source_probe_sha256", "")), "source probe hash missing")
    require(expected.get("toolchain", {}).get("cargo") and expected["toolchain"].get("rustc"), "toolchain binding missing")
    require(sha256(root / "tools/aggregate_com_semantic_replay_v2.py") == expected["aggregate_runner_sha256"], "aggregate runner hash drift")
    require(sha256(root / "tools/run_com_clean_archive_contract_tests_v2.py") == expected["contract_test_runner_sha256"], "contract runner hash drift")
    evidence = document.get("evidence", {})
    report_items = evidence.get("reports", [])
    require(len(report_items) == 2, "two report bindings required")
    parsed: list[dict[str, Any]] = []
    for item in report_items:
        path = root / item["path"]
        require(path.is_file() and sha256(path) == item["sha256"], "report hash drift")
        report = json.loads(path.read_text(encoding="utf-8"))
        require(not has_absolute_path(report), "absolute path leaked into report")
        require(report.get("schema") == f"sipi.{mode_key}.direct-semantic-replay.v2", "report schema drift")
        require(report.get("run_id") == item.get("run_id"), "run ID binding drift")
        binding = report.get("execution_binding", {})
        nonce = binding.get("nonce", "")
        require(HEX64.fullmatch(nonce), "nonce must be 64 lowercase hex characters")
        require(report.get("source", {}).get("commit") == upstream["commit"], "report upstream commit drift")
        require(report.get("source", {}).get("tree") == upstream["tree"], "report upstream tree drift")
        require(report.get("upstream") == upstream | {"repository": "https://github.com/z331225718/agent-com.git"}, "report upstream metadata drift")
        require(report.get("candidate", {}).get("commit") == candidate["commit"], "report candidate drift")
        require(report.get("candidate", {}).get("tree") == candidate["tree"], "report tree drift")
        require(report.get("candidate", {}).get("archive_sha256") == candidate["archive_sha256"], "report archive drift")
        report_candidate = report.get("candidate", {})
        require(report_candidate.get("binary_sha256") in candidate["binary_sha256_by_run"], "report binary drift")
        require(report.get("semantic_replays_identical") is True and report.get("replay_count") == 2, "semantic replay drift")
        require(binding.get("runner", {}).get("sha256") == expected["runner_sha256"], "runner binding drift")
        require(binding.get("helper", {}).get("sha256") == expected["helper_sha256"], "helper binding drift")
        require(binding.get("v2_wrapper", {}).get("sha256") == expected["v2_wrapper_sha256"], "wrapper binding drift")
        require(binding.get("fixture", {}).get("corpus_sha256") == expected["fixture_corpus_sha256"], "fixture corpus drift")
        require(len(binding.get("fixture", {}).get("inputs", [])) == expected["input_count"], "fixture inputs drift")
        require(binding.get("source_probe", {}).get("source_sha256") == expected["source_probe_sha256"], "source probe drift")
        verify_tool(binding.get("toolchain", {}).get("cargo"), "cargo")
        verify_tool(binding.get("toolchain", {}).get("rustc"), "rustc")
        require(binding.get("toolchain", {}).get("path_redacted") is True, "toolchain redaction drift")
        require(binding.get("toolchain") == expected.get("toolchain"), "toolchain manifest binding drift")
        verify_build(binding.get("build"), candidate, report_candidate)
        probe = binding.get("source_probe", {})
        require(probe.get("s2p_uses_validated_fd_to_td_leaf") is True and probe.get("s4p_uses_validated_fd_to_td_leaf") is True, "FD-to-TD leaf probe failed")
        require(probe.get("s2p_forbids_matched_kernel") is True and probe.get("s4p_forbids_matched_kernel") is True, "matched-kernel probe failed")
        parsed.append(report)
    require(parsed[0]["run_id"] != parsed[1]["run_id"], "run IDs must be distinct")
    require(parsed[0]["execution_binding"]["nonce"] != parsed[1]["execution_binding"]["nonce"], "nonces must be distinct")
    require(parsed[0]["execution_binding"]["toolchain"] == parsed[1]["execution_binding"]["toolchain"], "toolchain is not exact across runs")
    build_keys = ("command", "returncode", "timeout_seconds", "timed_out", "rustc_wrapper_cleared", "source_mode", "source_commit", "source_tree", "archive_sha256")
    require(all(parsed[0]["execution_binding"]["build"].get(key) == parsed[1]["execution_binding"]["build"].get(key) for key in build_keys), "build source binding drift")
    require(parsed[0]["replays"][0]["semantic"] == parsed[1]["replays"][0]["semantic"], "fresh semantic payload drift")
    aggregate_path = root / evidence["aggregate"]["path"]
    require(sha256(aggregate_path) == evidence["aggregate"]["sha256"], "aggregate hash drift")
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    require(not has_absolute_path(aggregate), "absolute path leaked into aggregate")
    require(aggregate.get("schema") == f"sipi.{mode_key}.direct-semantic-replay-aggregate.v2", "aggregate schema drift")
    require(aggregate.get("report_sha256") == [item["sha256"] for item in report_items], "aggregate report binding drift")
    require(aggregate.get("toolchain_exact_equal") is True and aggregate.get("build_source_exact_equal") is True, "aggregate exact binding drift")
    require(aggregate.get("binary_sha256_by_run") == [report["candidate"]["binary_sha256"] for report in parsed], "aggregate binary binding drift")
    require(aggregate.get("upstream") == parsed[0]["upstream"], "aggregate upstream drift")
    rust_tests = evidence.get("clean_archive_rust_tests", {})
    rust_path = root / rust_tests["path"]
    require(sha256(rust_path) == rust_tests["sha256"], "Rust test evidence drift")
    rust = json.loads(rust_path.read_text(encoding="utf-8"))
    require(rust.get("returncode") == 0 and rust.get("tests", {}).get("passed") == 49, "clean archive Rust tests failed")
    verification = document.get("verification", {})
    verifier_path = root / verification["verifier"]
    mutation_path = root / verification["mutation_tests"]
    require(sha256(verifier_path) == verification["verifier_sha256"], "verifier hash drift")
    require(sha256(mutation_path) == verification["mutation_tests_sha256"], "mutation hash drift")
    return {"schema": document["schema"], "reports": 2, "nonce_64_hex": True, "toolchain_exact_equal": True, "archive_derived_binary": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.manifest), sort_keys=True))
    except (OSError, KeyError, TypeError, yaml.YAMLError, VerificationError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
