"""Verify the bounded two-run evidence for the PyBERT native source corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import yaml
try:  # pragma: no cover - direct execution uses the fallback
    from . import run_pb_02_native_source_corpus as runner
except ImportError:  # pragma: no cover
    import run_pb_02_native_source_corpus as runner


ROOT = Path(__file__).resolve().parents[1]
PREP_PARENT = "d2047cd1"
PREP_PATHS = (
    "tools/run_pb_02_native_source_corpus.py",
    "tools/verify_pb_02_native_source_corpus.py",
    "tools/test_pb_02_native_source_corpus.py",
    "docs/baselines/pb-02-pinned-native-source-corpus-prep.v1.yaml",
    "docs/baselines/audits/2026-09-02-pb-02-pinned-native-source-corpus-prep.md",
)
MAX_REPORT_BYTES = 128 * 1024 * 1024
HEX40 = set("0123456789abcdef")
HEX64 = set("0123456789abcdef")


class VerifyError(RuntimeError):
    pass


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_REPORT_BYTES:
        raise VerifyError("report must be a bounded regular file")
    payload = path.read_bytes()
    if len(payload) != path.stat().st_size:
        raise VerifyError("report changed during read")

    def pairs(items: list[tuple[Any, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise VerifyError("JSON object keys must be unique strings")
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(VerifyError("non-finite JSON literal")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerifyError("report is not UTF-8 JSON") from error
    if type(value) is not dict:
        raise VerifyError("report root must be an object")
    _finite(value)
    return value, payload


def _finite(value: Any, depth: int = 0) -> None:
    if depth > 128:
        raise VerifyError("report nesting budget exceeded")
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise VerifyError("report contains a non-finite value")
        return
    if type(value) is list:
        for item in value:
            _finite(item, depth + 1)
        return
    if type(value) is dict:
        for item in value.values():
            _finite(item, depth + 1)
        return
    raise VerifyError("report contains an unsupported JSON type")


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise VerifyError(f"{label} key set drift")
    return value


def _hex(value: Any, length: int, label: str) -> str:
    if type(value) is not str or len(value) != length or any(char not in (HEX40 if length == 40 else HEX64) for char in value):
        raise VerifyError(f"{label} must be lowercase hexadecimal")
    return value


def _validate_tool(value: Any, label: str) -> dict[str, Any]:
    item = _exact(value, {"role", "executable", "file_sha256", "version_sha256", "version_exit", "path_redacted"}, label)
    if type(item["role"]) is not str or type(item["executable"]) is not str or "/" in item["executable"] or "\\" in item["executable"]:
        raise VerifyError(f"{label} identity drift")
    _hex(item["file_sha256"], 64, f"{label}.file_sha256")
    _hex(item["version_sha256"], 64, f"{label}.version_sha256")
    if item["version_exit"] != 0 or item["path_redacted"] is not True:
        raise VerifyError(f"{label} probe must pass without a path")
    return item


def _validate_success(case: dict[str, Any]) -> None:
    if case.get("kind") != "complete_native_artifact" or case.get("passed") is not True:
        raise VerifyError(f"successful case did not pass: {case.get('id')}")
    _validate_input(case.get("input"))
    for role in ("candidate_process", "oracle_process"):
        if case.get(role, {}).get("exit_code") != 0:
            raise VerifyError(f"successful case process failed: {case.get('id')}")
    comparison = _exact(case.get("comparison"), {"metadata", "arrays", "artifacts"}, "successful comparison")
    metadata = _exact(comparison["metadata"], {"passed", "drifts", "excluded_paths"}, "metadata comparison")
    if metadata["passed"] is not True or metadata["drifts"] != [] or metadata["excluded_paths"] != list(runner.METADATA_EXCLUSIONS):
        raise VerifyError("metadata acceptance drift")
    arrays = _exact(comparison["arrays"], {"passed", "drifts", "members"}, "array comparison")
    if arrays["passed"] is not True or arrays["drifts"] != [] or type(arrays["members"]) is not list or not arrays["members"]:
        raise VerifyError("array acceptance drift")
    for member in arrays["members"]:
        if type(member) is not dict or member.get("present") is not True or member.get("passed") is not True:
            raise VerifyError("array member did not pass")
    artifacts = _exact(comparison["artifacts"], {"candidate", "oracle"}, "artifact comparison")
    for role in ("candidate", "oracle"):
        item = _exact(artifacts[role], {"meta", "arrays"}, f"{role} artifacts")
        for kind in ("meta", "arrays"):
            receipt = _exact(item[kind], {"bytes", "sha256"}, f"{role}.{kind}")
            if type(receipt["bytes"]) is not int or receipt["bytes"] < 1:
                raise VerifyError("artifact bytes drift")
            _hex(receipt["sha256"], 64, "artifact sha256")


def _validate_rejection(case: dict[str, Any]) -> None:
    if case.get("kind") != "expected_rejection" or case.get("passed") is not True:
        raise VerifyError("rejection case did not pass")
    _validate_input(case.get("input"))
    if case.get("error_category") != "additive_noise_length_mismatch" or case.get("no_artifacts") != {"candidate": True, "oracle": True}:
        raise VerifyError("rejection semantics drift")
    if case.get("candidate_process", {}).get("exit_code") == 0 or case.get("oracle_process", {}).get("exit_code") == 0:
        raise VerifyError("rejection process unexpectedly succeeded")


def _validate_input(value: Any) -> dict[str, Any]:
    item = _exact(value, {"bytes", "sha256", "file"}, "case input")
    if type(item["bytes"]) is not int or item["bytes"] < 1 or type(item["file"]) is not dict:
        raise VerifyError("case input receipt drift")
    _hex(item["sha256"], 64, "case input sha256")
    return item


def _validate_report(value: dict[str, Any]) -> dict[str, Any]:
    report = _exact(value, {"schema", "version", "run_id", "nonce", "status", "scope", "candidate", "upstream", "toolchain", "build", "oracle_runtime", "cases"}, "report")
    if report["schema"] != runner.SCHEMA or report["version"] != 1 or report["status"] != "passed":
        raise VerifyError("report status or schema drift")
    if type(report["run_id"]) is not str or not report["run_id"]:
        raise VerifyError("run_id missing")
    _hex(report["nonce"], 64, "nonce")
    scope = _exact(report["scope"], {"source_test_path", "source_test_blob", "successful_case_ids", "rejection_case_id", "numeric_rtol", "numeric_atol", "metadata_exclusions"}, "scope")
    if scope["source_test_path"] != runner.SOURCE_TEST_PATH or scope["source_test_blob"] != runner.SOURCE_TEST_BLOB or tuple(scope["successful_case_ids"]) != runner.SUCCESS_CASES or scope["rejection_case_id"] != runner.REJECTION_CASE or scope["numeric_rtol"] != runner.NUMERIC_RTOL or scope["numeric_atol"] != runner.NUMERIC_ATOL or tuple(scope["metadata_exclusions"]) != runner.METADATA_EXCLUSIONS:
        raise VerifyError("scope drift")
    for role, expected in (("candidate", None), ("upstream", runner.PINNED_UPSTREAM)):
        item = report[role]
        required = {"commit", "tree", "archive_sha256"} | ({"fixture"} if role == "candidate" else set())
        item = _exact(item, required, role)
        _hex(item["commit"], 40, f"{role}.commit")
        _hex(item["tree"], 40, f"{role}.tree")
        _hex(item["archive_sha256"], 64, f"{role}.archive_sha256")
        if expected is not None and item["commit"] != expected:
            raise VerifyError("upstream commit drift")
    fixture = _exact(report["candidate"]["fixture"], {"path", "bytes", "sha256"}, "fixture")
    if fixture["path"] != runner.FIXTURE or type(fixture["bytes"]) is not int or fixture["bytes"] < 1:
        raise VerifyError("fixture binding drift")
    _hex(fixture["sha256"], 64, "fixture.sha256")
    tools = _exact(report["toolchain"], {"cargo", "rustc", "uv", "link"}, "toolchain")
    for role in tools:
        _validate_tool(tools[role], f"toolchain.{role}")
    if type(report["build"]) is not dict or type(report["oracle_runtime"]) is not dict:
        raise VerifyError("build or oracle receipt missing")
    if type(report["cases"]) is not list or len(report["cases"]) != len(runner.CASE_IDS):
        raise VerifyError("case count drift")
    by_id = {case.get("id"): case for case in report["cases"] if type(case) is dict}
    if set(by_id) != set(runner.CASE_IDS):
        raise VerifyError("case identifiers drift")
    for case_id in runner.SUCCESS_CASES:
        _validate_success(by_id[case_id])
    _validate_rejection(by_id[runner.REJECTION_CASE])
    return report


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout.decode("ascii").strip()


def verify_preparation(repo: Path, prep_commit: str) -> dict[str, Any]:
    prep = _git(repo, "rev-parse", f"{prep_commit}^{{commit}}")
    parent = _git(repo, "rev-parse", f"{prep}^")
    if parent != _git(repo, "rev-parse", f"{PREP_PARENT}^{{commit}}"):
        raise VerifyError("preparation commit must be a direct child of the current source candidate")
    changed = _git(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", prep).splitlines()
    expected = [f"A\t{path}" for path in PREP_PATHS]
    if sorted(changed) != sorted(expected):
        raise VerifyError("preparation changed set drift")
    return {"commit": prep, "tree": _git(repo, "rev-parse", f"{prep}^{{tree}}"), "parent": parent, "paths": list(PREP_PATHS)}


def aggregate(reports: list[Path], output: Path) -> dict[str, Any]:
    if len(reports) != 2 or reports[0].resolve() == reports[1].resolve():
        raise VerifyError("exactly two distinct report paths are required")
    loaded = [_validate_report(_strict_json(path)[0]) for path in reports]
    payloads = [_strict_json(path)[1] for path in reports]
    if loaded[0]["run_id"] == loaded[1]["run_id"] or loaded[0]["nonce"] == loaded[1]["nonce"]:
        raise VerifyError("replays must have distinct run IDs and nonces")
    shared = ("scope", "candidate", "upstream", "toolchain")
    for key in shared:
        if loaded[0][key] != loaded[1][key]:
            raise VerifyError(f"cross-run {key} drift")
    first_cases = {case["id"]: {"bytes": case["input"]["bytes"], "sha256": case["input"]["sha256"]} for case in loaded[0]["cases"]}
    second_cases = {case["id"]: {"bytes": case["input"]["bytes"], "sha256": case["input"]["sha256"]} for case in loaded[1]["cases"]}
    if first_cases != second_cases:
        raise VerifyError("cross-run canonical input drift")
    result = {
        "schema": "sipi.pb-02-pinned-native-source-corpus-aggregate.v1",
        "status": "passed",
        "reports": [{"name": path.name, "sha256": _sha256(payload), "bytes": len(payload), "run_id": item["run_id"], "nonce": item["nonce"]} for path, payload, item in zip(reports, payloads, loaded, strict=True)],
        "candidate": loaded[0]["candidate"],
        "upstream": loaded[0]["upstream"],
        "scope": loaded[0]["scope"],
        "case_ids": list(runner.CASE_IDS),
        "non_claims": ["This accepts only the pinned source-owned native corpus.", "AMI, IBIS, GetWave, S2P, vendor models, local extensions, Web/GUI families, release, and performance remain outside this record.", "The historical PB-01/PB-02 blocked matrix remains immutable historical evidence."],
    }
    if output.exists() or output.is_symlink():
        raise VerifyError("aggregate output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(json.dumps(result, sort_keys=True, indent=2).encode("utf-8") + b"\n")
    return result


def _record_path(value: Any) -> Path:
    if type(value) is not str:
        raise VerifyError("record path must be a string")
    path = (ROOT / value).resolve()
    if ROOT.resolve() not in path.parents or not path.is_file() or path.is_symlink():
        raise VerifyError("record path must be a regular workspace file")
    return path


def validate_record(record_path: Path, repo: Path) -> dict[str, Any]:
    if not record_path.is_file() or record_path.is_symlink():
        raise VerifyError("record must be a regular file")
    try:
        record = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise VerifyError("record YAML is invalid") from error
    record = _exact(record, {"schema", "status", "preparation", "candidate", "upstream", "reports", "aggregate", "scope", "non_claims"}, "record")
    if record["schema"] != "sipi.pb-02-pinned-native-source-corpus.v1" or record["status"] != "accepted_scoped_native_source_corpus":
        raise VerifyError("record schema or status drift")
    prep = _exact(record["preparation"], {"commit", "tree", "parent"}, "record preparation")
    checked_prep = verify_preparation(repo, prep["commit"])
    if prep != {key: checked_prep[key] for key in ("commit", "tree", "parent")}:
        raise VerifyError("record preparation receipt drift")
    if type(record["reports"]) is not list or len(record["reports"]) != 2:
        raise VerifyError("record requires exactly two reports")
    paths: list[Path] = []
    report_values: list[dict[str, Any]] = []
    for receipt in record["reports"]:
        receipt = _exact(receipt, {"path", "bytes", "sha256", "run_id", "nonce"}, "record report")
        path = _record_path(receipt["path"])
        value, payload = _strict_json(path)
        checked = _validate_report(value)
        if {"bytes": len(payload), "sha256": _sha256(payload), "run_id": checked["run_id"], "nonce": checked["nonce"]} != {key: receipt[key] for key in ("bytes", "sha256", "run_id", "nonce")}:
            raise VerifyError("record report receipt drift")
        paths.append(path)
        report_values.append(checked)
    aggregate_receipt = _exact(record["aggregate"], {"path", "bytes", "sha256"}, "record aggregate")
    aggregate_path = _record_path(aggregate_receipt["path"])
    aggregate_value, aggregate_payload = _strict_json(aggregate_path)
    if {"bytes": len(aggregate_payload), "sha256": _sha256(aggregate_payload)} != {key: aggregate_receipt[key] for key in ("bytes", "sha256")}:
        raise VerifyError("record aggregate receipt drift")
    expected = {"schema", "status", "reports", "candidate", "upstream", "scope", "case_ids", "non_claims"}
    aggregate_value = _exact(aggregate_value, expected, "aggregate record")
    if aggregate_value["status"] != "passed" or aggregate_value["candidate"] != report_values[0]["candidate"] or aggregate_value["upstream"] != report_values[0]["upstream"] or aggregate_value["scope"] != report_values[0]["scope"] or aggregate_value["case_ids"] != list(runner.CASE_IDS):
        raise VerifyError("aggregate record drift")
    if record["candidate"] != report_values[0]["candidate"] or record["upstream"].get("commit") != report_values[0]["upstream"]["commit"] or record["upstream"].get("tree") != report_values[0]["upstream"]["tree"] or record["upstream"].get("archive_sha256") != report_values[0]["upstream"]["archive_sha256"]:
        raise VerifyError("record source identity drift")
    if record["scope"] != report_values[0]["scope"]:
        raise VerifyError("record scope drift")
    return {"status": "valid", "record": record_path.name, "reports": [path.name for path in paths], "aggregate": aggregate_path.name}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prep-commit")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--reports", type=Path, nargs=2)
    parser.add_argument("--aggregate", type=Path)
    parser.add_argument("--record", type=Path)
    args = parser.parse_args()
    result: dict[str, Any] = {}
    if args.prep_commit:
        result["preparation"] = verify_preparation(args.repo, args.prep_commit)
    if args.reports is not None:
        if args.aggregate is None:
            raise VerifyError("--aggregate is required with --reports")
        result["aggregate"] = aggregate(args.reports, args.aggregate)
    if args.record is not None:
        result["record"] = validate_record(args.record, args.repo)
    if not result:
        raise VerifyError("select --prep-commit and/or --reports")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
