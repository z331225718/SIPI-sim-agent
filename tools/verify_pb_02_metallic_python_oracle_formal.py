"""Fail-closed verifier for the additive PB-02 metallic formal replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/pb-02-metallic-python-oracle-current-a94.v1.yaml"
CANDIDATE = {
    "commit": "dc82489d109f27b70940a5f1037cb08d3c10a8b6",
    "tree": "6311d5a0e88cd008e22ab9dcc0e7c18f57120ed3",
    "archive_sha256": "dcf9e38aaf0980c40a6c7640e5c229ac851a11e7c287d4bde386b21b1e9c5b00",
}
UPSTREAM = {
    "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
    "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
    "archive_sha256": "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25",
}
PREP = {"commit": "a94f2dcc566193a516878621a5042374faa7d1a9", "tree": "b2b89027af44962acd1736715a6651d830d5c187", "archive_sha256": "ea444506433cd4600fa2f0b386ebc821811abf3fb291e9ecc6f69435cfd2163c"}
CORPUS = "docs/baselines/pb-02-metallic-python-oracle-corpus.v1.json"
FIXTURE = "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml"
CASES = ["metallic-ctle-ordinary-3ghz-10ghz", "metallic-ctle-near-integral-3ghz"]
FIELDS = [
    "channel_impulse_v_per_v", "channel_output_v", "legacy_channel_frequency_hz", "legacy_channel_raw_re", "legacy_channel_raw_im",
    "legacy_channel_terminated_re", "legacy_channel_terminated_im", "legacy_channel_trimmed_re", "legacy_channel_trimmed_im",
    "rx_filter_impulse_v_per_v", "legacy_stage_ctle_re", "legacy_stage_ctle_im", "legacy_stage_ctle_out_re", "legacy_stage_ctle_out_im",
    "ctle_output_v", "rx_output_v", "dfe_output_v",
]
HARNESS_PATHS = {
    "matrix": "tools/run_pb_03_python_oracle_matrix.py",
    "oracle": "tools/pb_02_metallic_python_oracle.py",
    "runner": "tools/run_pb_02_metallic_python_oracle.py",
    "aggregate": "tools/aggregate_pb_02_metallic_python_oracle.py",
    "prep_verifier": "tools/verify_pb_02_metallic_python_oracle.py",
    "prep_test": "tools/test_verify_pb_02_metallic_python_oracle.py",
    "corpus": CORPUS,
    "formal_verifier": "tools/verify_pb_02_metallic_python_oracle_formal.py",
    "formal_test": "tools/test_verify_pb_02_metallic_python_oracle_formal.py",
}
SOURCE_MODE = "git_archive_at_candidate_prep_commit_plus_content_addressed_input_corpus_and_harness_snapshot"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")
REPORT_KEYS = {"build", "candidate", "cases", "claims", "corpus", "external_blockers", "fixture", "fresh_run_nonce", "harness", "non_claims", "row", "run_id", "schema", "scope", "source_mode", "status", "toolchain", "upstream", "version"}
CASE_KEYS = {"blockers", "candidate", "candidate_process", "expected_fields", "id", "oracle", "oracle_process", "payload", "status"}
META_KEYS = {"array_names", "backend", "diagnostics", "metrics", "schema", "source_command"}
PROCESS_KEYS = {"exit_code", "stderr_sha256", "stdout_sha256"}
PAYLOAD_KEYS = {"compared_field_count", "equal", "fields"}
BUILD_KEYS = {"binary_custody", "binary_sha256", "environment_policy", "exit_code", "stderr_sha256", "stdout_sha256"}
CUSTODY_KEYS = {"bytes", "canonical_sha256", "characteristics", "format", "machine", "normalization", "profile", "raw_sha256", "repro_entry", "schema"}
REPRO_KEYS = {"bytes", "debug_directory_index", "present", "raw_sha256"}
NORMALIZATION_KEYS = {"changed_byte_count", "fields", "map", "ranges"}
PE_BYTES = 3346944
NORMALIZATION_MAP = "zero-only:IMAGE_FILE_HEADER.TimeDateStamp+IMAGE_DEBUG_DIRECTORY.TimeDateStamp+CodeView.RSDS.GUID"
NORMALIZATION_FIELDS = ["IMAGE_FILE_HEADER.TimeDateStamp", "IMAGE_DEBUG_DIRECTORY[0].TimeDateStamp", "IMAGE_DEBUG_DIRECTORY[1].TimeDateStamp", "IMAGE_DEBUG_DIRECTORY[2].TimeDateStamp", "CodeView.RSDS[0].GUID"]
NORMALIZATION_RANGE_KEYS = {"canonical_hex", "field", "length", "offset", "raw_hex"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def keys(value: Any) -> set[Any] | None:
    return set(value) if isinstance(value, dict) else None


def load_json(root: Path, path: str, blockers: list[str], label: str) -> tuple[dict[str, Any] | None, str | None]:
    check(blockers, isinstance(path, str) and not Path(path).is_absolute() and ".." not in Path(path).parts, f"{label} path invalid")
    if not isinstance(path, str):
        return None, None
    try:
        payload = (root / path).read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        blockers.append(f"{label} cannot be loaded")
        return None, None
    check(blockers, isinstance(value, dict), f"{label} is not an object")
    return value if isinstance(value, dict) else None, hashlib.sha256(payload).hexdigest()


def summary_valid(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"dtype", "shape", "count", "f64_sha256"}:
        return False
    shape = value.get("shape")
    return value.get("dtype") == "float64" and isinstance(shape, list) and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in shape) and isinstance(value.get("count"), int) and value["count"] >= 0 and math.prod(shape) == value["count"] and isinstance(value.get("f64_sha256"), str) and HEX64.fullmatch(value["f64_sha256"]) is not None


def toolchain_valid(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"timeout_seconds", "cargo", "rustc", "uv", "python", "child_python", "host_python"} or not isinstance(value.get("timeout_seconds"), int) or value["timeout_seconds"] <= 0:
        return False
    for role in ("cargo", "rustc", "uv", "python"):
        item = value.get(role)
        if not isinstance(item, dict) or set(item) != {"role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"}:
            return False
        if item.get("role") != role or item.get("path_redacted") is not True or item.get("version_exit_code") != 0 or HEX64.fullmatch(str(item.get("file_sha256"))) is None or HEX64.fullmatch(str(item.get("version_output_sha256"))) is None:
            return False
    child = value.get("child_python")
    if not isinstance(child, dict) or set(child) != {"command", "identity", "process"} or child.get("command") != "uv run --project <archive> --frozen python -c <identity>":
        return False
    if not isinstance(child.get("process"), dict) or child["process"].get("exit_code") != 0 or set(child["process"]) != {"exit_code", "stderr_json", "stderr_sha256", "stdout_sha256"}:
        return False
    identity = child.get("identity")
    if not isinstance(identity, dict) or set(identity) != {"python", "numpy", "scipy"}:
        return False
    python = identity["python"]
    if not isinstance(python, dict) or set(python) != {"executable", "file_sha256", "implementation", "version", "path_redacted"} or python.get("path_redacted") is not True or HEX64.fullmatch(str(python.get("file_sha256"))) is None:
        return False
    if not isinstance(identity.get("numpy"), dict) or not isinstance(identity.get("scipy"), dict) or set(identity["numpy"]) != {"module", "version", "core_module"} or set(identity["scipy"]) != {"module", "version"}:
        return False
    host = value.get("host_python")
    process = child["process"]
    if not all(HEX64.fullmatch(str(process.get(key))) is not None for key in ("stderr_sha256", "stdout_sha256")) or process.get("stderr_json") != identity:
        return False
    return isinstance(host, dict) and set(host) == {"executable", "file_sha256", "path_redacted", "source"} and host.get("path_redacted") is True and HEX64.fullmatch(str(host.get("file_sha256"))) is not None


def report_shape_valid(report: dict[str, Any], blockers: list[str], label: str) -> None:
    check(blockers, set(report) == REPORT_KEYS, f"{label} top-level schema drift")
    check(blockers, keys(report.get("candidate")) == {"archive_sha256", "commit", "tree"} and keys(report.get("upstream")) == {"archive_sha256", "commit", "tree"}, f"{label} source schema drift")
    check(blockers, keys(report.get("fixture")) == {"archive_present", "archive_source_sha256", "path", "sha256", "source"}, f"{label} fixture schema drift")
    check(blockers, keys(report.get("corpus")) == {"case_count", "file_names", "path", "sha256"}, f"{label} corpus schema drift")
    harness = report.get("harness", {})
    if not isinstance(harness, dict):
        harness = {}
    check(blockers, set(harness) == {"runner", "python_oracle", "wrapper"} and set(harness.get("runner", {})) == {"path", "sha256"} and set(harness.get("wrapper", {})) == {"path", "sha256"} and set(harness.get("python_oracle", {})) == {"path", "sha256", "snapshot"}, f"{label} harness schema drift")
    build = report.get("build", {})
    if not isinstance(build, dict):
        build = {}
    custody = build.get("binary_custody", {})
    if not isinstance(custody, dict):
        custody = {}
    check(blockers, keys(build) == BUILD_KEYS and keys(custody) == CUSTODY_KEYS and keys(custody.get("repro_entry")) == REPRO_KEYS and keys(custody.get("normalization")) == NORMALIZATION_KEYS, f"{label} build/PE schema drift")
    raw_cases = report.get("cases")
    check(blockers, isinstance(raw_cases, list) and len(raw_cases) == 2 and all(isinstance(case, dict) and set(case) == CASE_KEYS for case in raw_cases), f"{label} case schema drift")


def verify_report(report: dict[str, Any], blockers: list[str], label: str, root: Path = ROOT) -> None:
    report_shape_valid(report, blockers, label)
    check(blockers, report.get("schema") == "sipi.pb-02-metallic-python-oracle-replay.v1", f"{label} schema drift")
    check(blockers, report.get("source_mode") == SOURCE_MODE, f"{label} source mode drift")
    check(blockers, report.get("candidate") == CANDIDATE, f"{label} candidate drift")
    check(blockers, report.get("upstream") == UPSTREAM, f"{label} upstream drift")
    check(blockers, report.get("status") == "blocked", f"{label} overall status drift")
    claims = report.get("claims")
    check(blockers, claims == {"global_branch_parity": False, "independent_python_payload_oracle": True, "near_integral_counted_as_parity": False, "near_integral_external_blocked": True, "ordinary_payload_parity": True, "promotion": False}, f"{label} claims drift")
    fixture = report.get("fixture") or {}
    check(blockers, fixture.get("path") == FIXTURE and fixture.get("archive_present") is True, f"{label} fixture drift")
    check(blockers, report.get("corpus", {}).get("path") == CORPUS and report.get("corpus", {}).get("sha256") == sha256(root / CORPUS), f"{label} corpus path/hash drift")
    check(blockers, fixture.get("sha256") == sha256(root / FIXTURE), f"{label} fixture hash drift")
    harness = report.get("harness", {})
    check(blockers, set(harness) == {"runner", "python_oracle", "wrapper"}, f"{label} harness key drift")
    for key, path in (("runner", HARNESS_PATHS["matrix"]), ("python_oracle", HARNESS_PATHS["oracle"]), ("wrapper", HARNESS_PATHS["runner"])):
        item = harness.get(key, {})
        check(blockers, item.get("path") == path and item.get("sha256") == sha256(root / path), f"{label} harness {key} drift")
    check(blockers, toolchain_valid(report.get("toolchain")), f"{label} toolchain/child identity drift")
    policy = {"rustc_wrapper_cleared": True, "rustc_workspace_wrapper_cleared": True, "cargo_build_rustc_wrapper_cleared": True}
    check(blockers, report.get("build", {}).get("environment_policy") == policy, f"{label} wrapper policy drift")
    custody = report.get("build", {}).get("binary_custody", {})
    check(blockers, report.get("build", {}).get("binary_sha256") == custody.get("raw_sha256") and HEX64.fullmatch(str(custody.get("raw_sha256"))) is not None and HEX64.fullmatch(str(custody.get("canonical_sha256"))) is not None and custody.get("bytes") == PE_BYTES and custody.get("format") == "PE" and custody.get("machine") == 34404 and custody.get("characteristics") == 34 and custody.get("profile") == "pe32-plus" and custody.get("schema") == "sipi.windows-pe-replay-custody.v1", f"{label} PE custody drift")
    repro = custody.get("repro_entry", {})
    check(blockers, repro == {"bytes": 0, "debug_directory_index": None, "present": False, "raw_sha256": None}, f"{label} REPRO policy drift")
    normalization = custody.get("normalization", {})
    check(blockers, normalization.get("map") == NORMALIZATION_MAP and normalization.get("fields") == NORMALIZATION_FIELDS and isinstance(normalization.get("changed_byte_count"), int) and normalization["changed_byte_count"] >= 0, f"{label} normalization policy drift")
    ranges = normalization.get("ranges", [])
    check(blockers, isinstance(ranges, list) and len(ranges) == len(NORMALIZATION_FIELDS) and [item.get("field") for item in ranges] == NORMALIZATION_FIELDS, f"{label} normalization range count/field drift")
    spans: list[tuple[int, int]] = []
    if isinstance(ranges, list):
        for item in ranges:
            valid = isinstance(item, dict) and set(item) == NORMALIZATION_RANGE_KEYS and isinstance(item.get("offset"), int) and isinstance(item.get("length"), int) and item["offset"] >= 0 and item["length"] > 0 and item["offset"] + item["length"] <= PE_BYTES and isinstance(item.get("raw_hex"), str) and isinstance(item.get("canonical_hex"), str)
            if valid:
                valid = len(item["raw_hex"]) == 2 * item["length"] and len(item["canonical_hex"]) == 2 * item["length"] and all(character in "0123456789abcdef" for character in item["raw_hex"] + item["canonical_hex"])
                spans.append((item["offset"], item["offset"] + item["length"]))
            check(blockers, valid, f"{label} normalization range drift")
    ordered = sorted(spans)
    check(blockers, all(left[1] <= right[0] for left, right in zip(ordered, ordered[1:])), f"{label} normalization ranges overlap")
    check(blockers, isinstance(ranges, list) and normalization.get("changed_byte_count") == sum(item["length"] for item in ranges if isinstance(item, dict) and isinstance(item.get("length"), int)), f"{label} normalization byte count drift")
    cases = report.get("cases")
    check(blockers, isinstance(cases, list) and [case.get("id") for case in cases] == CASES, f"{label} case order drift")
    if not isinstance(cases, list) or len(cases) != 2 or not all(isinstance(case, dict) for case in cases):
        return
    for case in cases:
        check(blockers, set(case) == CASE_KEYS and set(case.get("candidate_process", {})) == PROCESS_KEYS and set(case.get("oracle_process", {})) == PROCESS_KEYS and set(case.get("candidate", {})) == META_KEYS and set(case.get("oracle", {})) == META_KEYS and set(case.get("payload", {})) == PAYLOAD_KEYS, f"{label} nested case schema drift")
    ordinary, near = cases
    for case in cases:
        candidate_meta = case.get("candidate", {})
        oracle_meta = case.get("oracle", {})
        check(blockers, candidate_meta.get("schema") == "pybert.native-cli-result.v1", f"{label} candidate schema drift")
        check(blockers, oracle_meta.get("schema") == "pybert.python-oracle-result.v1" and oracle_meta.get("backend") == "python" and oracle_meta.get("source_command") == "PythonSimulationBackend", f"{label} independent oracle schema drift")
        for process_key in ("candidate_process", "oracle_process"):
            process = case.get(process_key, {})
            check(blockers, all(HEX64.fullmatch(str(process.get(key))) is not None for key in ("stderr_sha256", "stdout_sha256")), f"{label} process hash schema drift")
    check(blockers, ordinary.get("status") == "passed" and ordinary.get("blockers") == [], f"{label} ordinary status drift")
    check(blockers, ordinary.get("candidate_process", {}).get("exit_code") == 0 and ordinary.get("oracle_process", {}).get("exit_code") == 0, f"{label} ordinary exit drift")
    payload = ordinary.get("payload", {})
    fields = payload.get("fields", [])
    check(blockers, payload.get("equal") is True and payload.get("compared_field_count") == 17 and [field.get("name") for field in fields] == FIELDS and all(field.get("passed") is True for field in fields), f"{label} ordinary payload drift")
    for field in fields:
        metrics_valid = all(isinstance(field.get(key), (int, float)) and not isinstance(field.get(key), bool) and math.isfinite(float(field[key])) and field[key] >= 0 for key in ("max_abs", "scale", "tolerance"))
        check(blockers, set(field) == {"name", "candidate", "oracle", "max_abs", "scale", "tolerance", "passed"} and summary_valid(field.get("candidate")) and summary_valid(field.get("oracle")) and field["candidate"]["shape"] == field["oracle"]["shape"] and field["candidate"]["count"] == field["oracle"]["count"] and metrics_valid and field["passed"] is (field["max_abs"] <= field["tolerance"]), f"{label} payload summary drift")
    check(blockers, near.get("status") == "blocked" and near.get("blockers") == ["pinned_channel_cubic_interp1d_two_point_boundary"], f"{label} near status drift")
    check(blockers, near.get("candidate_process", {}).get("exit_code") == 0 and near.get("oracle_process", {}).get("exit_code") == 1, f"{label} near exit drift")
    check(blockers, near.get("payload", {}).get("equal") is False and near.get("payload", {}).get("fields") == [] and near.get("payload", {}).get("compared_field_count") == 0, f"{label} near payload drift")
    diagnostics = near.get("oracle", {}).get("diagnostics", {})
    check(blockers, diagnostics.get("failure_code") == "pinned_channel_cubic_interp1d_two_point_boundary" and diagnostics.get("failure_stage") == "channel", f"{label} near blocker drift")
    check(blockers, PATH_LEAK.search(json.dumps(report, ensure_ascii=True)) is None, f"{label} path leak")


def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    try:
        import verify_pb_02_metallic_python_oracle as prep_verifier
        prep_result = prep_verifier.verify_prep(prep_verifier.prep_document(), ROOT)
        check(blockers, prep_result.get("valid") is True, "prep verifier gate failed")
    except (OSError, ValueError, json.JSONDecodeError):
        blockers.append("prep verifier unavailable")
    expected_keys = {"schema", "version", "row", "status", "source_mode", "candidate", "upstream", "prep", "source", "harness", "evidence", "audit", "claims"}
    check(blockers, set(document) == expected_keys, "manifest key set drift")
    check(blockers, document.get("schema") == "sipi.pb-02-metallic-python-oracle-current-a94.v1", "manifest schema drift")
    check(blockers, document.get("status") == "blocked_external_python_oracle", "manifest status drift")
    check(blockers, document.get("claims") == {"ordinary_payload_parity": True, "near_integral_external_blocked": True, "near_integral_counted_as_parity": False, "global_branch_parity": False, "promotion": False}, "manifest claims drift")
    check(blockers, keys(document.get("candidate")) == {"commit", "tree", "archive_sha256"} and keys(document.get("upstream")) == {"commit", "tree", "archive_sha256"} and keys(document.get("prep")) == {"commit", "tree", "archive_sha256"}, "manifest identity schema drift")
    check(blockers, document.get("candidate") == CANDIDATE and document.get("upstream") == UPSTREAM and document.get("prep") == PREP, "manifest source identity drift")
    check(blockers, document.get("source_mode") == SOURCE_MODE, "manifest source mode drift")
    source = document.get("source", {})
    check(blockers, keys(source) == {"corpus_path", "corpus_sha256", "fixture_path", "fixture_sha256"}, "manifest source schema drift")
    if not isinstance(source, dict):
        source = {}
    check(blockers, source.get("corpus_path") == CORPUS and source.get("fixture_path") == FIXTURE, "manifest corpus/fixture path drift")
    check(blockers, sha256(root / CORPUS) == source.get("corpus_sha256") and sha256(root / FIXTURE) == source.get("fixture_sha256"), "manifest corpus/fixture hash drift")
    harness = document.get("harness", {})
    check(blockers, keys(harness) == set(HARNESS_PATHS), "manifest harness key set drift")
    if not isinstance(harness, dict):
        harness = {}
    for role, path in HARNESS_PATHS.items():
        item = harness.get(role, {})
        if role == "corpus":
            actual_hash = sha256(root / path)
        else:
            actual_hash = sha256(root / path)
        check(blockers, isinstance(item, dict) and set(item) == {"path", "sha256"} and item.get("path") == path and not Path(path).is_absolute() and ".." not in Path(path).parts and actual_hash == item.get("sha256"), f"harness {role} drift")
    evidence = document.get("evidence", {})
    check(blockers, keys(evidence) == {"reports", "aggregate"}, "manifest evidence schema drift")
    if not isinstance(evidence, dict):
        evidence = {}
    bindings = evidence.get("reports", [])
    if not isinstance(bindings, list):
        bindings = []
    loaded: list[dict[str, Any]] = []
    if not isinstance(bindings, list) or len(bindings) != 2:
        blockers.append("exactly two report bindings are required")
    else:
        for index, binding in enumerate(bindings, 1):
            check(blockers, keys(binding) == {"path", "sha256", "run_id", "fresh_run_nonce"}, f"report-{index} binding schema drift")
            report, actual = load_json(root, binding.get("path"), blockers, f"report-{index}")
            check(blockers, actual == binding.get("sha256"), f"report-{index} hash drift")
            if report is not None:
                verify_report(report, blockers, f"report-{index}", root)
                check(blockers, report.get("run_id") == binding.get("run_id") and report.get("fresh_run_nonce") == binding.get("fresh_run_nonce"), f"report-{index} identity drift")
                loaded.append(report)
    if len(loaded) == 2:
        check(blockers, loaded[0].get("run_id") != loaded[1].get("run_id") and loaded[0].get("fresh_run_nonce") != loaded[1].get("fresh_run_nonce"), "fresh identity is duplicated")
        check(blockers, loaded[0].get("toolchain") == loaded[1].get("toolchain"), "toolchain drift")
        check(blockers, loaded[0].get("build", {}).get("binary_custody", {}).get("canonical_sha256") == loaded[1].get("build", {}).get("binary_custody", {}).get("canonical_sha256"), "canonical PE drift")
        check(blockers, loaded[0].get("build", {}).get("binary_custody", {}).get("bytes") == loaded[1].get("build", {}).get("binary_custody", {}).get("bytes"), "PE byte count drift")
    aggregate_binding = evidence.get("aggregate", {})
    check(blockers, keys(aggregate_binding) == {"path", "sha256"}, "aggregate binding schema drift")
    if not isinstance(aggregate_binding, dict):
        aggregate_binding = {}
    aggregate, actual = load_json(root, aggregate_binding.get("path"), blockers, "aggregate")
    check(blockers, actual == aggregate_binding.get("sha256"), "aggregate hash drift")
    if aggregate is not None:
        check(blockers, aggregate.get("schema") == "sipi.pb-02-metallic-python-oracle-aggregate.v2-prep" and aggregate.get("status") == "blocked_near_integral_external", "aggregate status drift")
        check(blockers, aggregate.get("claims", {}).get("ordinary_payload_parity") is True and aggregate.get("claims", {}).get("near_integral_external_blocked") is True and aggregate.get("claims", {}).get("promotion") is False, "aggregate claims drift")
        check(blockers, PATH_LEAK.search(json.dumps(aggregate, ensure_ascii=True)) is None, "aggregate path leak")
        try:
            import aggregate_pb_02_metallic_python_oracle as aggregator
            previous_root = aggregator.ROOT
            try:
                aggregator.ROOT = root
                with tempfile.TemporaryDirectory(dir=root) as temporary:
                    regenerated_path = Path(temporary) / "aggregate.json"
                    aggregator.aggregate([root / binding["path"] for binding in bindings], regenerated_path)
                    check(blockers, regenerated_path.read_bytes() == (root / aggregate_binding["path"]).read_bytes(), "aggregate canonical regeneration drift")
            finally:
                aggregator.ROOT = previous_root
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append("aggregate validation failed")
    audit = document.get("audit", {})
    check(blockers, keys(audit) == {"path", "sha256"}, "audit binding schema drift")
    if not isinstance(audit, dict):
        audit = {}
    audit_path = audit.get("path")
    check(blockers, isinstance(audit_path, str) and audit_path not in {binding.get("path") for binding in bindings} and audit_path != aggregate_binding.get("path") and sha256(root / audit_path) == audit.get("sha256"), "audit hash/path drift")
    if isinstance(audit_path, str):
        audit_text = (root / audit_path).read_text(encoding="utf-8")
        check(blockers, "schema: sipi.pb-02-metallic-python-oracle-audit.v1" in audit_text and "nonclaims:" in audit_text, "audit schema/nonclaims drift")
    check(blockers, PATH_LEAK.search(json.dumps(document, ensure_ascii=True)) is None, "manifest path leak")
    return {"valid": not blockers, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    try:
        result = verify(yaml.safe_load(args.manifest.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValueError) as error:
        result = {"valid": False, "blockers": [str(error)]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
