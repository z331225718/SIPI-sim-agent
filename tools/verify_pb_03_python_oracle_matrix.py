"""Fail-closed verifier for the additive PB-03 Python-oracle matrix."""

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
REPORT_ONE = ROOT / "docs/baselines/pb-03-python-oracle-matrix-d315-run-01.v1.json"
REPORT_TWO = ROOT / "docs/baselines/pb-03-python-oracle-matrix-d315-run-02.v1.json"
AGGREGATE = ROOT / "docs/baselines/pb-03-python-oracle-matrix-d315-aggregate.v1.json"
BRANCH_MANIFEST = ROOT / "docs/baselines/pb-03-python-oracle-18-branch-d3154093.v1.yaml"
BRANCH_AUDIT = ROOT / "docs/baselines/audits/2026-08-24-pb-03-python-oracle-18-branch-d3154093.md"
MATRIX_MANIFEST = ROOT / "docs/baselines/pb-03-python-oracle-matrix-d3154093.v1.yaml"
CORPUS = ROOT / "docs/baselines/pb-03-python-oracle-corpus-d3154093.v1.json"
CANDIDATE_COMMIT = "884b430bee61d365793a3810beaeb76f58bee25c"
CANDIDATE_TREE = "d87b058e754eea1ae5f104df034a81b4b13dcb1d"
CANDIDATE_ARCHIVE = "1b19a54bd4a3517a698a55b85b316e1e85658b611b3674881930303df1fb56dd"
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
UPSTREAM_ARCHIVE = "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25"
FIXTURE_SHA = "2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f"
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")
CASE_IDS = {"nrz-base", "pam4-noise-dfe", "duo-noise-dfe", "pam4-viterbi-isi", "pam4-viterbi-fec", "nrz-s2p", "nrz-analytic-ctle"}
TOOLCHAIN_KEYS = {"timeout_seconds", "cargo", "rustc", "uv", "python"}
TOOL_KEYS = {"role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"}
BUILD_KEYS = {"exit_code", "stdout_sha256", "stderr_sha256", "binary_sha256", "binary_custody"}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def manifest_binding(document: Any) -> str:
    if not isinstance(document, dict) or not isinstance(document.get("corpus"), dict):
        return ""
    corpus = document["corpus"]
    core = {
        "schema": document.get("schema"),
        "version": document.get("version"),
        "successor_of": document.get("successor_of"),
        "row": document.get("row"),
        "status": document.get("status"),
        "purpose": document.get("purpose"),
        "source": document.get("source"),
        "corpus": {key: corpus.get(key) for key in ("path", "sha256", "cases")},
        "branch_inventory": document.get("branch_inventory"),
        "portable_branch_probe_missing": document.get("portable_branch_probe_missing"),
        "python_payload_oracle_missing": document.get("python_payload_oracle_missing"),
        "external_blockers": document.get("external_blockers"),
        "claims": document.get("claims"),
    }
    return sha256(json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def verify_toolchain(value: Any, errors: list[str], label: str) -> None:
    check(errors, isinstance(value, dict) and set(value) == TOOLCHAIN_KEYS, f"{label}: toolchain keys drift")
    if not isinstance(value, dict):
        return
    check(errors, isinstance(value.get("timeout_seconds"), int) and value["timeout_seconds"] > 0, f"{label}: timeout drift")
    for role in ("cargo", "rustc", "uv", "python"):
        item = value.get(role)
        check(errors, isinstance(item, dict) and set(item) == TOOL_KEYS, f"{label}: {role} keys drift")
        if not isinstance(item, dict):
            continue
        executable = item.get("executable")
        check(errors, item.get("role") == role, f"{label}: {role} role drift")
        check(errors, isinstance(executable, str) and executable and Path(executable).name == executable and "/" not in executable and "\\" not in executable, f"{label}: {role} executable drift")
        check(errors, item.get("path_redacted") is True, f"{label}: {role} path disclosure")
        check(errors, isinstance(item.get("file_sha256"), str) and HEX64.fullmatch(item["file_sha256"]) is not None, f"{label}: {role} file hash drift")
        check(errors, item.get("version_exit_code") == 0, f"{label}: {role} version exit drift")
        check(errors, isinstance(item.get("version_output_sha256"), str) and HEX64.fullmatch(item["version_output_sha256"]) is not None, f"{label}: {role} version hash drift")


def verify_build(value: Any, errors: list[str], label: str) -> None:
    check(errors, isinstance(value, dict) and set(value) == BUILD_KEYS, f"{label}: build keys drift")
    if not isinstance(value, dict):
        return
    check(errors, isinstance(value.get("exit_code"), int), f"{label}: build exit drift")
    for key in ("stdout_sha256", "stderr_sha256"):
        check(errors, isinstance(value.get(key), str) and HEX64.fullmatch(value[key]) is not None, f"{label}: build {key} drift")
    if value.get("exit_code") == 0:
        check(errors, isinstance(value.get("binary_sha256"), str) and HEX64.fullmatch(value["binary_sha256"]) is not None, f"{label}: successful build lacks binary hash")
        custody = value.get("binary_custody")
        check(errors, not validate_windows_pe_replay_custody(custody), f"{label}: PE custody schema drift")
    elif value.get("binary_custody") is not None:
        check(errors, not validate_windows_pe_replay_custody(value.get("binary_custody")), f"{label}: failed-build PE custody drift")
    if isinstance(value.get("binary_custody"), dict):
        check(errors, value.get("binary_sha256") == value["binary_custody"].get("raw_sha256"), f"{label}: raw binary/custody digest split")


def safe_relative(path: Any) -> bool:
    if not isinstance(path, str):
        return False
    value = Path(path)
    return not value.is_absolute() and ".." not in value.parts


def forbidden_claim(value: Any) -> bool:
    if isinstance(value, dict):
        return any(forbidden_claim(key) or forbidden_claim(item) for key, item in value.items())
    if isinstance(value, list):
        return any(forbidden_claim(item) for item in value)
    if isinstance(value, str):
        lower = value.lower()
        return "overlay" in lower or "working_tree" in lower or "working-tree" in lower
    return False


def verify_report(report: Any, root: Path, label: str) -> list[str]:
    errors: list[str] = []
    check(errors, isinstance(report, dict), f"{label}: report is not an object")
    if not isinstance(report, dict):
        return errors
    check(errors, report.get("schema") == "sipi.pb-03-python-oracle-matrix-replay.v1", f"{label}: schema mismatch")
    check(errors, report.get("row") == "PB-03", f"{label}: row mismatch")
    check(errors, report.get("source_mode") == "git_archive_at_candidate_prep_commit_plus_content_addressed_input_corpus_and_harness_snapshot", f"{label}: source mode mismatch")
    check(errors, report.get("status") == "blocked", f"{label}: report must remain blocked")
    check(errors, not forbidden_claim(report), f"{label}: forbidden overlay/working-tree claim")
    check(errors, PATH_LEAK.search(json.dumps(report, ensure_ascii=True, sort_keys=True)) is None, f"{label}: absolute path leaked")
    nonce = report.get("fresh_run_nonce")
    check(errors, isinstance(nonce, str) and HEX32.fullmatch(nonce) is not None, f"{label}: malformed fresh nonce")
    check(errors, isinstance(report.get("run_id"), str) and report["run_id"], f"{label}: run_id missing")
    candidate = report.get("candidate")
    check(errors, isinstance(candidate, dict), f"{label}: candidate identity missing")
    if isinstance(candidate, dict):
        check(errors, candidate.get("commit") == CANDIDATE_COMMIT, f"{label}: candidate commit drift")
        check(errors, candidate.get("tree") == CANDIDATE_TREE, f"{label}: candidate tree drift")
        check(errors, candidate.get("archive_sha256") == CANDIDATE_ARCHIVE, f"{label}: candidate archive drift")
    upstream = report.get("upstream")
    check(errors, isinstance(upstream, dict), f"{label}: upstream identity missing")
    if isinstance(upstream, dict):
        check(errors, upstream.get("commit") == UPSTREAM_COMMIT, f"{label}: upstream commit drift")
        check(errors, upstream.get("tree") == UPSTREAM_TREE, f"{label}: upstream tree drift")
        check(errors, upstream.get("archive_sha256") == UPSTREAM_ARCHIVE, f"{label}: upstream archive drift")
    fixture = report.get("fixture")
    check(errors, isinstance(fixture, dict), f"{label}: fixture record missing")
    if isinstance(fixture, dict):
        check(errors, fixture.get("archive_present") is True, f"{label}: fixture archive_present is false")
        check(errors, fixture.get("path") == "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml", f"{label}: fixture path drift")
        check(errors, fixture.get("sha256") == FIXTURE_SHA, f"{label}: fixture hash drift")
        check(errors, fixture.get("source") == "candidate_archive", f"{label}: fixture source drift")
        check(errors, fixture.get("archive_source_sha256") == FIXTURE_SHA, f"{label}: fixture archive source hash drift")
    corpus = report.get("corpus")
    check(errors, isinstance(corpus, dict), f"{label}: corpus binding missing")
    if isinstance(corpus, dict):
        check(errors, corpus.get("path") == "docs/baselines/pb-03-python-oracle-corpus-d3154093.v1.json", f"{label}: corpus path drift")
        check(errors, corpus.get("sha256") == sha256(CORPUS.read_bytes()), f"{label}: corpus hash drift")
        check(errors, corpus.get("case_count") == len(CASE_IDS), f"{label}: corpus case count drift")
        check(errors, corpus.get("file_names") == ["pb-03-ctle.s2p", "pb-03-s2p.s2p"], f"{label}: corpus file set drift")
    harness = report.get("harness")
    check(errors, isinstance(harness, dict), f"{label}: harness binding missing")
    if isinstance(harness, dict):
        check(errors, set(harness) == {"runner", "python_oracle"}, f"{label}: harness keys drift")
        for key in ("runner", "python_oracle"):
            item = harness.get(key)
            check(errors, isinstance(item, dict), f"{label}: harness {key} missing")
            if isinstance(item, dict):
                allowed = {"path", "sha256", "snapshot"} if key == "python_oracle" else {"path", "sha256"}
                check(errors, set(item) == allowed, f"{label}: harness {key} keys drift")
                relative = item.get("path")
                check(errors, safe_relative(relative), f"{label}: harness {key} path unsafe")
                if safe_relative(relative):
                    path = root / relative
                    check(errors, path.is_file(), f"{label}: harness {key} file missing")
                    if path.is_file():
                        check(errors, item.get("sha256") == sha256(path.read_bytes()), f"{label}: harness {key} hash drift")
                check(errors, isinstance(item.get("sha256"), str) and HEX64.fullmatch(item["sha256"]) is not None, f"{label}: harness {key} hash malformed")
                if key == "python_oracle":
                    check(errors, item.get("snapshot") == "candidate_prep_archive_harness_snapshot", f"{label}: oracle harness snapshot drift")
    verify_build(report.get("build"), errors, label)
    verify_toolchain(report.get("toolchain"), errors, label)
    claims = report.get("claims")
    check(errors, isinstance(claims, dict), f"{label}: claims missing")
    if isinstance(claims, dict):
        check(errors, claims.get("independent_python_payload_oracle") is True, f"{label}: Python oracle claim missing")
        check(errors, claims.get("global_branch_parity") is False, f"{label}: global parity claim was closed")
        check(errors, claims.get("promotion") is False, f"{label}: promotion claim was closed")
    cases = report.get("cases")
    check(errors, isinstance(cases, list), f"{label}: case matrix missing")
    seen: set[str] = set()
    if isinstance(cases, list):
        for case in cases:
            check(errors, isinstance(case, dict), f"{label}: case is not an object")
            if not isinstance(case, dict):
                continue
            case_id = case.get("id")
            check(errors, isinstance(case_id, str) and case_id in CASE_IDS, f"{label}: unknown case {case_id}")
            if isinstance(case_id, str):
                check(errors, case_id not in seen, f"{label}: duplicate case {case_id}")
                seen.add(case_id)
            check(errors, case.get("status") in {"passed", "blocked"}, f"{label}: invalid case status {case_id}")
            expected = case.get("expected_fields")
            check(errors, isinstance(expected, list) and bool(expected), f"{label}: expected fields missing {case_id}")
            candidate_meta = case.get("candidate")
            oracle_meta = case.get("oracle")
            if isinstance(oracle_meta, dict) and oracle_meta.get("schema") is not None:
                check(errors, oracle_meta.get("schema") == "pybert.python-oracle-result.v1", f"{label}: oracle schema drift {case_id}")
                check(errors, oracle_meta.get("backend") == "python", f"{label}: oracle backend drift {case_id}")
                check(errors, oracle_meta.get("source_command") == "PythonSimulationBackend", f"{label}: oracle command drift {case_id}")
            if isinstance(candidate_meta, dict) and candidate_meta.get("schema") is not None:
                check(errors, candidate_meta.get("schema") == "pybert.native-cli-result.v1", f"{label}: candidate schema drift {case_id}")
            process = case.get("oracle_process")
            check(errors, isinstance(process, dict) and isinstance(process.get("exit_code"), int), f"{label}: oracle process missing {case_id}")
            payload = case.get("payload")
            check(errors, isinstance(payload, dict), f"{label}: payload comparison missing {case_id}")
            if case.get("status") == "passed":
                check(errors, isinstance(candidate_meta, dict) and candidate_meta.get("schema") == "pybert.native-cli-result.v1", f"{label}: passed candidate schema missing {case_id}")
                check(errors, isinstance(oracle_meta, dict) and oracle_meta.get("schema") == "pybert.python-oracle-result.v1", f"{label}: passed oracle schema missing {case_id}")
                check(errors, isinstance(case.get("candidate_process"), dict) and case["candidate_process"].get("exit_code") == 0, f"{label}: passed candidate exit drift {case_id}")
                check(errors, isinstance(process, dict) and process.get("exit_code") == 0, f"{label}: passed oracle exit drift {case_id}")
                check(errors, isinstance(payload, dict) and payload.get("equal") is True, f"{label}: passed case lacks payload equality {case_id}")
                check(errors, isinstance(payload, dict) and payload.get("compared_field_count") == len(expected), f"{label}: passed field count drift {case_id}")
                fields = payload.get("fields") if isinstance(payload, dict) else None
                check(errors, isinstance(fields, list) and len(fields) == len(expected), f"{label}: passed field list drift {case_id}")
                if isinstance(fields, list):
                    names = [field.get("name") if isinstance(field, dict) else None for field in fields]
                    check(errors, names == expected, f"{label}: passed field names drift {case_id}")
                    check(errors, all(isinstance(field, dict) and field.get("passed") is True for field in fields), f"{label}: passed field gate drift {case_id}")
                check(errors, case.get("blockers") == [], f"{label}: passed case retains blockers {case_id}")
            elif isinstance(payload, dict):
                check(errors, payload.get("equal") is not True, f"{label}: blocked case claims payload equality {case_id}")
            if isinstance(payload, dict):
                fields = payload.get("fields")
                check(errors, isinstance(fields, list), f"{label}: payload fields missing {case_id}")
                if isinstance(fields, list):
                    for field in fields:
                        if isinstance(field, dict):
                            check(errors, field.get("name") in expected, f"{label}: unrequested payload field {case_id}")
    check(errors, seen == CASE_IDS, f"{label}: case set incomplete")
    return errors


def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    errors = verify_report(document, root, "report")
    return {"valid": not errors, "errors": errors}


def verify_pair(first: dict[str, Any], second: dict[str, Any], aggregate: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    errors = verify_report(first, root, "first") + verify_report(second, root, "second")
    check(errors, first.get("run_id") != second.get("run_id"), "run IDs must be distinct")
    check(errors, first.get("fresh_run_nonce") != second.get("fresh_run_nonce"), "fresh nonces must be distinct")
    check(errors, first.get("candidate") == second.get("candidate"), "candidate identity drift")
    check(errors, first.get("upstream") == second.get("upstream"), "upstream identity drift")
    check(errors, first.get("toolchain") == second.get("toolchain"), "toolchain identity drift")
    check(errors, isinstance(aggregate, dict), "aggregate is not an object")
    if isinstance(aggregate, dict):
        check(errors, aggregate.get("schema") == "sipi.pb-03-python-oracle-matrix-aggregate.v1", "aggregate schema mismatch")
        check(errors, aggregate.get("status") == "blocked", "aggregate must remain blocked")
        check(errors, aggregate.get("source_mode") == "git_archive_at_candidate_prep_commit_plus_content_addressed_input_corpus_and_harness_snapshot", "aggregate source mode mismatch")
        check(errors, aggregate.get("claims", {}).get("independent_python_payload_oracle") is True, "aggregate oracle claim missing")
        check(errors, aggregate.get("claims", {}).get("global_branch_parity") is False, "aggregate global parity was closed")
        reports = aggregate.get("reports")
        check(errors, isinstance(reports, list) and len(reports) == 2, "aggregate report list malformed")
        if isinstance(reports, list) and len(reports) == 2:
            expected_reports = []
            for path, report in ((REPORT_ONE, first), (REPORT_TWO, second)):
                expected_reports.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "sha256": sha256(path.read_bytes()),
                        "run_id": report.get("run_id"),
                        "fresh_run_nonce": report.get("fresh_run_nonce"),
                    }
                )
            check(errors, reports == expected_reports, "aggregate report binding does not match actual reports")
            for report in reports:
                check(errors, safe_relative(report.get("path")), "aggregate report path unsafe")
                digest = report.get("sha256")
                check(errors, isinstance(digest, str) and HEX64.fullmatch(digest) is not None, "aggregate report hash malformed")
            check(errors, reports[0].get("sha256") != reports[1].get("sha256"), "aggregate report digests are not distinct")
            check(errors, reports[0].get("run_id") != reports[1].get("run_id"), "aggregate run IDs are not distinct")
            check(errors, reports[0].get("fresh_run_nonce") != reports[1].get("fresh_run_nonce"), "aggregate nonces are not distinct")
        check(errors, aggregate.get("candidate") == first.get("candidate"), "aggregate candidate identity drift")
        check(errors, aggregate.get("upstream") == first.get("upstream"), "aggregate upstream identity drift")
        check(errors, aggregate.get("fixture") == first.get("fixture"), "aggregate fixture identity drift")
        check(errors, aggregate.get("corpus") == first.get("corpus"), "aggregate corpus identity drift")
        check(errors, aggregate.get("harness") == first.get("harness"), "aggregate harness identity drift")
        check(errors, aggregate.get("toolchain") == first.get("toolchain"), "aggregate toolchain identity drift")
        expected_builds = [
            {
                "report": REPORT_ONE.relative_to(root).as_posix(),
                "binary_sha256": first.get("build", {}).get("binary_sha256") if isinstance(first.get("build"), dict) else None,
                "binary_custody": first.get("build", {}).get("binary_custody") if isinstance(first.get("build"), dict) else None,
            },
            {
                "report": REPORT_TWO.relative_to(root).as_posix(),
                "binary_sha256": second.get("build", {}).get("binary_sha256") if isinstance(second.get("build"), dict) else None,
                "binary_custody": second.get("build", {}).get("binary_custody") if isinstance(second.get("build"), dict) else None,
            },
        ]
        check(errors, aggregate.get("builds") == expected_builds, "aggregate binary binding drift")
        check(
            errors,
            not compare_windows_pe_custody(
                first.get("build", {}).get("binary_custody") if isinstance(first.get("build"), dict) else None,
                second.get("build", {}).get("binary_custody") if isinstance(second.get("build"), dict) else None,
            ),
            "aggregate PE custody gate drift",
        )
        custody_gate = aggregate.get("binary_custody_gate")
        check(errors, isinstance(custody_gate, dict), "aggregate PE custody gate missing")
        if isinstance(custody_gate, dict):
            check(
                errors,
                set(custody_gate) == {"raw_sha256_equal", "canonical_sha256_equal", "normalization_shape_equal", "repro_policy", "blockers"},
                "aggregate PE custody gate keys drift",
            )
            first_custody = first.get("build", {}).get("binary_custody") if isinstance(first.get("build"), dict) else None
            second_custody = second.get("build", {}).get("binary_custody") if isinstance(second.get("build"), dict) else None
            check(errors, custody_gate.get("raw_sha256_equal") == (first.get("build", {}).get("binary_sha256") == second.get("build", {}).get("binary_sha256")), "aggregate raw PE gate drift")
            check(errors, custody_gate.get("canonical_sha256_equal") == (isinstance(first_custody, dict) and isinstance(second_custody, dict) and first_custody.get("canonical_sha256") == second_custody.get("canonical_sha256")), "aggregate canonical PE gate drift")
            check(errors, custody_gate.get("normalization_shape_equal") == (windows_pe_custody_shape(first_custody) == windows_pe_custody_shape(second_custody)), "aggregate PE normalization gate drift")
            check(errors, custody_gate.get("repro_policy") == windows_pe_repro_policy(first_custody, second_custody), "aggregate REPRO policy drift")
            check(errors, custody_gate.get("blockers") == compare_windows_pe_custody(first_custody, second_custody), "aggregate PE gate blocker drift")
        distinct = aggregate.get("distinct_gate")
        if isinstance(distinct, dict):
            check(errors, distinct.get("exact_binary_canonical_sha256") is True, "aggregate canonical PE reproducibility gate drift")
        try:
            matrix_manifest = yaml.safe_load(MATRIX_MANIFEST.read_text(encoding="utf-8"))
            manifest_harness = matrix_manifest.get("harness") if isinstance(matrix_manifest, dict) else None
            check(errors, isinstance(manifest_harness, dict), "matrix manifest harness missing")
            if isinstance(manifest_harness, dict):
                for name, binding in manifest_harness.items():
                    check(errors, isinstance(binding, dict), f"matrix manifest harness {name} malformed")
                    if isinstance(binding, dict):
                        path_text = binding.get("path")
                        check(errors, isinstance(path_text, str) and safe_relative(path_text), f"matrix manifest harness {name} path drift")
                        if isinstance(path_text, str) and safe_relative(path_text):
                            check(errors, binding.get("sha256") == sha256((root / path_text).read_bytes()), f"matrix manifest harness {name} hash drift")
            manifest = yaml.safe_load(BRANCH_MANIFEST.read_text(encoding="utf-8"))
            check(errors, aggregate.get("manifest") == {"path": "docs/baselines/pb-03-python-oracle-18-branch-d3154093.v1.yaml", "binding_sha256": manifest_binding(manifest)}, "aggregate manifest binding drift")
            check(errors, aggregate.get("audit") == {"path": "docs/baselines/audits/2026-08-24-pb-03-python-oracle-18-branch-d3154093.md", "sha256": sha256(BRANCH_AUDIT.read_bytes())}, "aggregate audit binding drift")
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            errors.append("aggregate manifest/audit cannot be loaded")
        check(errors, not forbidden_claim(aggregate), "aggregate contains overlay claim")
        check(errors, PATH_LEAK.search(json.dumps(aggregate, ensure_ascii=True, sort_keys=True)) is None, "aggregate absolute path leaked")
    return {"valid": not errors, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPORT_ONE)
    parser.add_argument("--second", type=Path, default=REPORT_TWO)
    parser.add_argument("--aggregate", type=Path, default=AGGREGATE)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        first = json.loads(args.report.read_text(encoding="utf-8"))
        second = json.loads(args.second.read_text(encoding="utf-8"))
        aggregate = json.loads(args.aggregate.read_text(encoding="utf-8"))
        result = verify_pair(first, second, aggregate, args.root.resolve())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        result = {"valid": False, "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
