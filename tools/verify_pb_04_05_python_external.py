"""Fail-closed verifier for the PB-04/PB-05 Python external oracle successor."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from pb_03_replay_common import compare_windows_pe_custody, validate_windows_pe_replay_custody, windows_pe_custody_shape, windows_pe_repro_policy


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
CANDIDATE_COMMIT = "884b430bee61d365793a3810beaeb76f58bee25c"
CANDIDATE_TREE = "d87b058e754eea1ae5f104df034a81b4b13dcb1d"
CANDIDATE_ARCHIVE_SHA256 = "1b19a54bd4a3517a698a55b85b316e1e85658b611b3674881930303df1fb56dd"
UPSTREAM_ARCHIVE_SHA256 = "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25"
FIXTURE_SHA256 = "2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f"
NONCE = re.compile(r"[0-9a-f]{32,64}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")

MANIFESTS = {
    "PB-04": "docs/baselines/pb-04-python-external-d3154093.v1.yaml",
    "PB-05": "docs/baselines/pb-05-python-external-d3154093.v1.yaml",
}
AUDITS = {
    "PB-04": "docs/baselines/audits/2026-08-24-pb-04-python-external-d3154093.md",
    "PB-05": "docs/baselines/audits/2026-08-24-pb-05-python-external-d3154093.md",
}
TOOLCHAIN_KEYS = {"timeout_seconds", "cargo", "rustc", "uv", "python"}
TOOL_KEYS = {"role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"}
PROCESS_KEYS = {"exit_code", "stdout_sha256", "stderr_sha256", "stderr_json", "skipped", "error"}
BUILD_KEYS = {"exit_code", "stdout_sha256", "stderr_sha256", "binary_sha256", "binary_custody"}

ROWS = {
    "PB-04": {
        "one": "docs/baselines/pb-04-python-external-d315-run-01.v1.json",
        "two": "docs/baselines/pb-04-python-external-d315-run-02.v1.json",
        "aggregate": "docs/baselines/pb-04-python-external-d315-aggregate.v1.json",
    },
    "PB-05": {
        "one": "docs/baselines/pb-05-python-external-d315-run-01.v1.json",
        "two": "docs/baselines/pb-05-python-external-d315-run-02.v1.json",
        "aggregate": "docs/baselines/pb-05-python-external-d315-aggregate.v1.json",
    },
}


def digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def repo_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def path_free(value: Any) -> bool:
    return PATH_LEAK.search(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)) is None


def manifest_binding(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    core = {key: item for key, item in value.items() if key not in {"evidence", "harness", "verification", "audit"}}
    return hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def exact_keys(errors: list[str], value: Any, allowed: set[str], label: str) -> None:
    check(errors, isinstance(value, dict), f"{label} is not an object")
    if isinstance(value, dict):
        check(errors, set(value) == allowed, f"{label} keys drift")


def verify_toolchain(value: Any, errors: list[str], label: str) -> None:
    exact_keys(errors, value, TOOLCHAIN_KEYS, label)
    if not isinstance(value, dict):
        return
    check(errors, isinstance(value.get("timeout_seconds"), int) and value["timeout_seconds"] > 0, f"{label} timeout drift")
    for tool_name in ("cargo", "rustc", "uv", "python"):
        item = value.get(tool_name)
        exact_keys(errors, item, TOOL_KEYS, f"{label}.{tool_name}")
        if not isinstance(item, dict):
            continue
        check(errors, item.get("role") == tool_name, f"{label}.{tool_name} role drift")
        executable = item.get("executable")
        check(errors, isinstance(executable, str) and executable and Path(executable).name == executable and "/" not in executable and "\\" not in executable, f"{label}.{tool_name} executable drift")
        check(errors, item.get("path_redacted") is True, f"{label}.{tool_name} path disclosure")
        check(errors, isinstance(item.get("file_sha256"), str) and HEX64.fullmatch(item["file_sha256"]) is not None, f"{label}.{tool_name} file digest drift")
        check(errors, item.get("version_exit_code") == 0, f"{label}.{tool_name} version exit drift")
        check(errors, isinstance(item.get("version_output_sha256"), str) and HEX64.fullmatch(item["version_output_sha256"]) is not None, f"{label}.{tool_name} version digest drift")


def verify_process(value: Any, errors: list[str], label: str, *, required_exit: int | None = None) -> None:
    exact_keys(errors, value, set(value) if isinstance(value, dict) else PROCESS_KEYS, label)
    if not isinstance(value, dict):
        return
    check(errors, set(value).issubset(PROCESS_KEYS), f"{label} keys drift")
    exit_code = value.get("exit_code")
    check(errors, isinstance(exit_code, int) or exit_code is None, f"{label} exit type drift")
    if required_exit is not None:
        check(errors, exit_code == required_exit, f"{label} exit drift")
    for key in ("stdout_sha256", "stderr_sha256"):
        if key in value:
            check(errors, isinstance(value[key], str) and HEX64.fullmatch(value[key]) is not None, f"{label}.{key} drift")
    if "stderr_json" in value:
        check(errors, isinstance(value["stderr_json"], dict), f"{label}.stderr_json drift")
    check(errors, path_free(value), f"{label} contains an absolute path")


def verify_build(value: Any, errors: list[str], label: str) -> None:
    exact_keys(errors, value, BUILD_KEYS, label)
    if not isinstance(value, dict):
        return
    check(errors, isinstance(value.get("exit_code"), int), f"{label} exit drift")
    for key in ("stdout_sha256", "stderr_sha256"):
        check(errors, isinstance(value.get(key), str) and HEX64.fullmatch(value[key]) is not None, f"{label}.{key} drift")
    if value.get("exit_code") == 0:
        check(errors, isinstance(value.get("binary_sha256"), str) and HEX64.fullmatch(value["binary_sha256"]) is not None, f"{label}.binary_sha256 missing after successful build")
        check(errors, not validate_windows_pe_replay_custody(value.get("binary_custody")), f"{label}.binary_custody schema drift")
    elif value.get("binary_custody") is not None:
        check(errors, not validate_windows_pe_replay_custody(value.get("binary_custody")), f"{label}.binary_custody failed-build drift")
    if isinstance(value.get("binary_custody"), dict):
        check(errors, value.get("binary_sha256") == value["binary_custody"].get("raw_sha256"), f"{label}.raw binary/custody digest split")
    if value.get("binary_sha256") is not None:
        check(errors, isinstance(value["binary_sha256"], str) and HEX64.fullmatch(value["binary_sha256"]) is not None, f"{label}.binary_sha256 drift")
    check(errors, path_free(value), f"{label} contains an absolute path")


def load(path: Path, errors: list[str], label: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(f"{label} cannot be loaded: {type(error).__name__}")
        return None, None
    check(errors, isinstance(value, dict), f"{label} is not an object")
    return value if isinstance(value, dict) else None, digest(path)


def verify_report(row: str, report: dict[str, Any], errors: list[str], label: str) -> None:
    check(errors, report.get("schema") == "sipi.pb-04-05-python-external-replay.v1", f"{label} schema drift")
    check(errors, report.get("row") == row, f"{label} row drift")
    check(errors, report.get("source_mode") == "git_archive_at_candidate_prep_commit_plus_candidate_archive_fixture_copy_and_harness_snapshot", f"{label} source overlay mode")
    check(errors, isinstance(report.get("run_id"), str) and report["run_id"], f"{label} run ID missing")
    check(errors, isinstance(report.get("fresh_run_nonce"), str) and NONCE.fullmatch(report.get("fresh_run_nonce", "")) is not None, f"{label} nonce malformed")
    candidate = report.get("candidate")
    check(errors, isinstance(candidate, dict), f"{label} candidate identity missing")
    if isinstance(candidate, dict):
        check(errors, candidate.get("commit") == CANDIDATE_COMMIT, f"{label} candidate commit drift")
        check(errors, candidate.get("tree") == CANDIDATE_TREE, f"{label} candidate tree drift")
        check(errors, candidate.get("archive_sha256") == CANDIDATE_ARCHIVE_SHA256, f"{label} candidate archive drift")
        check(errors, "working_tree_overlay" not in candidate, f"{label} candidate overlay claim present")
    upstream = report.get("upstream")
    check(errors, isinstance(upstream, dict), f"{label} upstream identity missing")
    if isinstance(upstream, dict):
        check(errors, upstream.get("commit") == UPSTREAM_COMMIT, f"{label} upstream commit drift")
        check(errors, upstream.get("tree") == UPSTREAM_TREE, f"{label} upstream tree drift")
        check(errors, upstream.get("archive_sha256") == UPSTREAM_ARCHIVE_SHA256, f"{label} upstream archive drift")
    fixture = report.get("fixture")
    check(errors, isinstance(fixture, dict), f"{label} fixture missing")
    if isinstance(fixture, dict):
        check(errors, fixture.get("archive_present") is True, f"{label} fixture archive gate drift")
        check(errors, fixture.get("path") == "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml", f"{label} fixture path drift")
        check(errors, fixture.get("sha256") == FIXTURE_SHA256, f"{label} fixture digest drift")
        check(errors, fixture.get("source") == "candidate_archive", f"{label} fixture source drift")
        check(errors, fixture.get("archive_source_sha256") == FIXTURE_SHA256, f"{label} fixture archive source drift")
        check(errors, fixture.get("oracle_copy") == "content_addressed_copy_from_candidate_archive", f"{label} fixture copy drift")
    harness = report.get("harness")
    check(errors, isinstance(harness, dict) and set(harness) == {"runner", "python_external_reference"}, f"{label} harness keys drift")
    if isinstance(harness, dict):
        for key in ("runner", "python_external_reference"):
            item = harness.get(key)
            check(errors, isinstance(item, dict), f"{label} {key} binding missing")
            if isinstance(item, dict):
                allowed = {"path", "sha256", "snapshot"} if key == "python_external_reference" else {"path", "sha256"}
                check(errors, set(item) == allowed, f"{label} {key} keys drift")
                check(errors, repo_relative(item.get("path")), f"{label} {key} path leak")
                check(errors, isinstance(item.get("sha256"), str) and HEX64.fullmatch(item["sha256"]) is not None, f"{label} {key} digest missing")
                if repo_relative(item.get("path")):
                    check(errors, digest(ROOT / item["path"]) == item.get("sha256"), f"{label} {key} digest drift")
                if key == "python_external_reference":
                    check(errors, item.get("snapshot") == "candidate_prep_archive_harness_snapshot", f"{label} external helper snapshot drift")
    oracle = report.get("oracle")
    check(errors, isinstance(oracle, dict) and oracle.get("independent") is True, f"{label} independent oracle claim missing")
    if isinstance(oracle, dict):
        check(errors, oracle.get("backend") == "python", f"{label} oracle backend drift")
        check(errors, oracle.get("source_command") == "PythonSimulationBackend", f"{label} oracle source drift")
        process = oracle.get("process")
        verify_process(process, errors, f"{label} oracle process", required_exit=0)
        reference = oracle.get("reference")
        check(errors, isinstance(reference, dict) and reference.get("present") is True, f"{label} reference artifact missing")
        if isinstance(reference, dict):
            check(errors, reference.get("schema") == "pybert.backend-run-result.v1", f"{label} reference schema drift")
            check(errors, reference.get("result_adapter_schema") == "pybert.engine.result_adapter.v1", f"{label} result adapter schema missing")
            check(errors, isinstance(reference.get("array_count"), int) and reference["array_count"] > 0, f"{label} reference arrays missing")
            check(errors, isinstance(reference.get("two_dimensional_arrays"), list) and bool(reference["two_dimensional_arrays"]), f"{label} two-dimensional eye payload missing")
            check(errors, isinstance(reference.get("sha256"), str) and HEX64.fullmatch(reference["sha256"]) is not None, f"{label} reference digest missing")
    check(errors, report.get("status") == "blocked", f"{label} must remain blocked")
    blockers = report.get("blockers")
    check(errors, isinstance(blockers, list) and bool(blockers), f"{label} blocker evidence missing")
    candidate_process = report.get("candidate_process")
    verify_process(candidate_process, errors, f"{label} candidate process")
    verify_build(report.get("build"), errors, f"{label} build")
    verify_toolchain(report.get("toolchain"), errors, f"{label} toolchain")
    claims = report.get("claims")
    check(errors, isinstance(claims, dict), f"{label} claims missing")
    if isinstance(claims, dict):
        check(errors, claims.get("same_crate_self_compare") is False, f"{label} same-crate comparison claim drift")
        check(errors, claims.get("global_row_closed") is False, f"{label} global closure claim drift")
        check(errors, claims.get("promotion") is False, f"{label} promotion claim drift")
        check(errors, claims.get("release_approval") is False, f"{label} release claim drift")
    if row == "PB-04":
        selection = report.get("selection")
        check(errors, isinstance(selection, dict), f"{label} selection diagnostics missing")
        if isinstance(selection, dict):
            check(errors, selection.get("requested") == "auto", f"{label} auto requested drift")
            check(errors, selection.get("selected") == "python", f"{label} auto selected drift")
            check(errors, selection.get("implementation") == "external_python_reference_required", f"{label} fallback substitution drift")
            check(errors, selection.get("rust_only") is False, f"{label} Rust-only fallback claim drift")
            gate = selection.get("parity_gate")
            check(errors, isinstance(gate, dict) and gate.get("status") == "blocked", f"{label} parity gate drift")
    else:
        comparison = report.get("comparison")
        check(errors, isinstance(comparison, dict), f"{label} comparison diagnostics missing")
        if isinstance(comparison, dict):
            check(errors, comparison.get("status_only_comparison") is False, f"{label} status-only comparison drift")
            check(errors, comparison.get("reason") == "not_evaluated", f"{label} missing external-reference fail-closed reason")
            check(errors, comparison.get("reference_required") == "external_python_reference_required", f"{label} external reference requirement drift")
        check(errors, isinstance(claims, dict) and claims.get("payload_compare") is False, f"{label} payload promotion drift")
    check(errors, path_free(report), f"{label} contains an absolute path")


def verify_manifest(
    row: str,
    manifest: dict[str, Any] | None,
    manifest_sha: str | None,
    reports: list[dict[str, Any]],
    report_bindings: list[dict[str, Any]],
    aggregate_sha: str | None,
    audit_sha: str | None,
    errors: list[str],
    root: Path,
) -> None:
    label = f"{row} manifest"
    check(errors, isinstance(manifest, dict), f"{label} is missing")
    if not isinstance(manifest, dict):
        return
    check(errors, manifest.get("row") == row, f"{label} row drift")
    check(errors, isinstance(manifest.get("schema"), str) and manifest["schema"].startswith(f"sipi.{row.lower()}-"), f"{label} schema drift")
    source = manifest.get("source")
    check(errors, isinstance(source, dict), f"{label} source missing")
    if isinstance(source, dict):
        expected_source = {
            "upstream_commit": UPSTREAM_COMMIT,
            "upstream_tree": UPSTREAM_TREE,
            "upstream_archive_sha256": UPSTREAM_ARCHIVE_SHA256,
            "candidate_commit": CANDIDATE_COMMIT,
            "candidate_tree": CANDIDATE_TREE,
            "candidate_archive_sha256": CANDIDATE_ARCHIVE_SHA256,
            "candidate_basis": "immutable_candidate_commit",
        }
        for key, expected in expected_source.items():
            check(errors, source.get(key) == expected, f"{label} source {key} drift")
    fixture = source.get("fixture") if isinstance(source, dict) else None
    check(errors, isinstance(fixture, dict), f"{label} fixture missing")
    if isinstance(fixture, dict):
        check(errors, fixture.get("path") == "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml", f"{label} fixture path drift")
        check(errors, fixture.get("archive_present") is True, f"{label} fixture archive gate drift")
        check(errors, fixture.get("sha256") == FIXTURE_SHA256, f"{label} fixture digest drift")
    evidence = manifest.get("evidence")
    check(errors, isinstance(evidence, dict), f"{label} evidence missing")
    if isinstance(evidence, dict):
        expected_reports = evidence.get("reports")
        check(errors, isinstance(expected_reports, list) and expected_reports == report_bindings, f"{label} report binding drift")
        aggregate = evidence.get("aggregate")
        check(errors, isinstance(aggregate, dict), f"{label} aggregate binding missing")
        if isinstance(aggregate, dict):
            check(errors, aggregate.get("path") == ROWS[row]["aggregate"], f"{label} aggregate path drift")
            check(errors, aggregate.get("sha256") == aggregate_sha, f"{label} aggregate digest drift")
    harness = manifest.get("harness")
    check(errors, isinstance(harness, dict), f"{label} harness missing")
    if isinstance(harness, dict):
        expected_harness = {
            "runner": "tools/run_pb_04_05_python_external.py",
            "oracle": "tools/pb_python_external_reference.py",
            "aggregator": "tools/aggregate_pb_04_05_python_external.py",
            "verifier": "tools/verify_pb_04_05_python_external.py",
            "mutation_tests": "tools/test_verify_pb_04_05_python_external.py",
        }
        check(errors, set(harness) == set(expected_harness), f"{label} harness keys drift")
        for key, path_text in expected_harness.items():
            item = harness.get(key)
            check(errors, isinstance(item, dict), f"{label} harness {key} missing")
            if isinstance(item, dict):
                check(errors, set(item) == {"path", "sha256"}, f"{label} harness {key} keys drift")
                check(errors, item.get("path") == path_text, f"{label} harness {key} path drift")
                check(errors, item.get("sha256") == digest(root / path_text), f"{label} harness {key} digest drift")
    audit = manifest.get("audit")
    check(errors, isinstance(audit, dict), f"{label} audit binding missing")
    if isinstance(audit, dict):
        check(errors, audit.get("path") == AUDITS[row], f"{label} audit path drift")
        check(errors, audit.get("sha256") == audit_sha, f"{label} audit digest drift")
    check(errors, isinstance(manifest_sha, str) and HEX64.fullmatch(manifest_sha) is not None, f"{label} digest missing")
    check(errors, path_free(manifest), f"{label} contains an absolute path")


def verify(row: str, root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    spec = ROWS[row]
    reports: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    for label, key in (("report-one", "one"), ("report-two", "two")):
        path = root / spec[key]
        value, actual = load(path, errors, label)
        if value is not None:
            verify_report(row, value, errors, label)
            reports.append(value)
            bindings.append({"path": spec[key], "sha256": actual, "run_id": value.get("run_id"), "fresh_run_nonce": value.get("fresh_run_nonce")})
    if len(reports) == 2:
        check(errors, reports[0].get("run_id") != reports[1].get("run_id"), "report run IDs are not independent")
        check(errors, reports[0].get("fresh_run_nonce") != reports[1].get("fresh_run_nonce"), "report nonces are not independent")
        check(errors, bindings[0]["sha256"] != bindings[1]["sha256"], "report digests are not independent")
        for key in ("candidate", "upstream", "fixture", "toolchain"):
            check(errors, reports[0].get(key) == reports[1].get(key), f"report {key} identity drift")
    aggregate_path = root / spec["aggregate"]
    aggregate, actual = load(aggregate_path, errors, "aggregate")
    if aggregate is not None:
        check(errors, aggregate.get("schema") == "sipi.pb-04-05-python-external-aggregate.v1", "aggregate schema drift")
        check(errors, aggregate.get("row") == row, "aggregate row drift")
        check(errors, aggregate.get("status") == "blocked", "aggregate must remain blocked")
        check(errors, aggregate.get("source_mode") == "git_archive_at_candidate_prep_commit_plus_candidate_archive_fixture_copy_and_harness_snapshot", "aggregate source mode drift")
        check(errors, isinstance(aggregate.get("blockers"), list) and bool(aggregate["blockers"]), "aggregate blockers missing")
        aggregate_reports = aggregate.get("reports")
        check(errors, aggregate_reports == bindings, "aggregate report binding drift")
        if reports:
            for key in ("candidate", "upstream", "fixture", "toolchain"):
                check(errors, aggregate.get(key) == reports[0].get(key), f"aggregate {key} drift")
        distinct = aggregate.get("distinct_gate")
        check(errors, isinstance(distinct, dict), "aggregate distinct gate missing")
        if isinstance(distinct, dict):
            for key in ("unique_report_paths", "unique_report_sha256", "unique_run_ids", "unique_fresh_run_nonces", "exact_toolchain_identity"):
                check(errors, distinct.get(key) is True, f"aggregate {key} drift")
            check(errors, distinct.get("exact_binary_canonical_sha256") is True, "aggregate canonical PE reproducibility gate drift")
        builds = aggregate.get("builds")
        expected_builds = [
            {
                "report": binding["path"],
                "binary_sha256": report.get("build", {}).get("binary_sha256") if isinstance(report.get("build"), dict) else None,
                "binary_custody": report.get("build", {}).get("binary_custody") if isinstance(report.get("build"), dict) else None,
            }
            for binding, report in zip(bindings, reports)
        ]
        check(errors, builds == expected_builds, "aggregate binary binding drift")
        if len(reports) == 2:
            first_custody = reports[0].get("build", {}).get("binary_custody")
            second_custody = reports[1].get("build", {}).get("binary_custody")
            check(errors, not compare_windows_pe_custody(first_custody, second_custody), "aggregate PE custody gate drift")
            custody_gate = aggregate.get("binary_custody_gate")
            check(errors, isinstance(custody_gate, dict), "aggregate PE custody gate missing")
            if isinstance(custody_gate, dict):
                check(errors, set(custody_gate) == {"raw_sha256_equal", "canonical_sha256_equal", "normalization_shape_equal", "repro_policy", "blockers"}, "aggregate PE custody gate keys drift")
                check(errors, custody_gate.get("raw_sha256_equal") == (reports[0].get("build", {}).get("binary_sha256") == reports[1].get("build", {}).get("binary_sha256")), "aggregate raw PE gate drift")
                check(errors, custody_gate.get("canonical_sha256_equal") == (isinstance(first_custody, dict) and isinstance(second_custody, dict) and first_custody.get("canonical_sha256") == second_custody.get("canonical_sha256")), "aggregate canonical PE gate drift")
                check(errors, custody_gate.get("normalization_shape_equal") == (windows_pe_custody_shape(first_custody) == windows_pe_custody_shape(second_custody)), "aggregate PE normalization gate drift")
                check(errors, custody_gate.get("repro_policy") == windows_pe_repro_policy(first_custody, second_custody), "aggregate REPRO policy drift")
                check(errors, custody_gate.get("blockers") == compare_windows_pe_custody(first_custody, second_custody), "aggregate PE gate blocker drift")
        manifest_path = root / MANIFESTS[row]
        audit_path = root / AUDITS[row]
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            check(errors, aggregate.get("manifest") == {"path": MANIFESTS[row], "binding_sha256": manifest_binding(manifest)}, "aggregate manifest binding drift")
            check(errors, aggregate.get("audit") == {"path": AUDITS[row], "sha256": digest(audit_path)}, "aggregate audit binding drift")
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            errors.append("aggregate manifest/audit cannot be loaded")
        claims = aggregate.get("claims")
        check(errors, isinstance(claims, dict) and claims.get("global_row_closed") is False and claims.get("promotion") is False, "aggregate claims drift")
        check(errors, path_free(aggregate), "aggregate contains an absolute path")
    manifest_path = root / MANIFESTS[row]
    manifest, manifest_sha = None, None
    try:
        manifest_payload = manifest_path.read_bytes()
        manifest = yaml.safe_load(manifest_payload.decode("utf-8"))
        manifest_sha = hashlib.sha256(manifest_payload).hexdigest()
        check(errors, isinstance(manifest, dict), "manifest is not an object")
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        errors.append("manifest cannot be loaded")
    audit_path = root / AUDITS[row]
    audit_sha = digest(audit_path)
    check(errors, audit_sha is not None, "audit cannot be loaded")
    verify_manifest(row, manifest, manifest_sha, reports, bindings, actual, audit_sha, errors, root)
    return {"valid": not errors, "row": row, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", choices=sorted(ROWS), required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = verify(args.row, args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
