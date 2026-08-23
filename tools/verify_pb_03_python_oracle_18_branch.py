"""Verify the additive PB-03 18-branch inventory without closing parity."""

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
MANIFEST = ROOT / "docs/baselines/pb-03-python-oracle-18-branch-d3154093.v1.yaml"
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
CANDIDATE_COMMIT = "d3154093fd58aeaa596444825dc17be6cb7e35c0"
CANDIDATE_TREE = "2d51e84554558bb4947c0152259af9bf7f927efe"
CANDIDATE_ARCHIVE_SHA256 = "693c95330b36f0a8068db3ce9a44bf4d45bfd1b73f47189d8149d67cfd909a24"
UPSTREAM_ARCHIVE_SHA256 = "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25"
FIXTURE_SHA256 = "2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
REPORT_PATHS = (
    "docs/baselines/pb-03-python-oracle-matrix-d315-run-01.v1.json",
    "docs/baselines/pb-03-python-oracle-matrix-d315-run-02.v1.json",
)
AGGREGATE_PATH = "docs/baselines/pb-03-python-oracle-matrix-d315-aggregate.v1.json"
AUDIT_PATH = "docs/baselines/audits/2026-08-24-pb-03-python-oracle-18-branch-d3154093.md"
CORPUS_CASES = ["nrz-base", "pam4-noise-dfe", "duo-noise-dfe", "pam4-viterbi-isi", "pam4-viterbi-fec", "nrz-s2p", "nrz-analytic-ctle"]

BRANCH_IDS = {
    "config.pybert_cfg_bounded_state_mapping",
    "config.pybert_cfg_protocol45_root_identity",
    "config.pybert_cfg_protocol45_nested_root_rejected",
    "legacy.modulation.nrz",
    "legacy.modulation.pam4_duo_binary",
    "legacy.pattern.supported_prbs",
    "legacy.channel.rlgc",
    "legacy.channel.s2p_touchstone",
    "legacy.channel.s1p_s4p_differential_renumber",
    "legacy.channel.touchstone_reference_R_two_column_step_impulse",
    "legacy.rx.ctle_s2p_file_parser",
    "legacy.tx_rx.ffe_dfe_cdr",
    "legacy.tx.periodic_random_noise",
    "legacy.tx.random_noise_seed_and_zero_seed_effective_state",
    "legacy.rx.viterbi_isi_fec_mapping",
    "legacy.analysis.jitter_eye_ber",
    "legacy.analysis.jitter_relative_threshold",
    "legacy.external.ami_ibis_ts4_getwave",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def path_free(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return not re.search(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)", text)


def manifest_binding(document: dict[str, Any]) -> str:
    corpus = document.get("corpus")
    if not isinstance(corpus, dict):
        return ""
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
    return digest_bytes(canonical(core))


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path, errors: list[str], label: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(f"{label} load failed: {type(error).__name__}")
        return None, None
    check(errors, isinstance(value, dict), f"{label} is not an object")
    return (value if isinstance(value, dict) else None), digest_bytes(payload)


def verify_toolchain(value: Any, errors: list[str], label: str) -> None:
    allowed = {"timeout_seconds", "cargo", "rustc", "uv", "python"}
    check(errors, isinstance(value, dict) and set(value) == allowed, f"{label} keys drift")
    if not isinstance(value, dict):
        return
    check(errors, isinstance(value.get("timeout_seconds"), int) and value["timeout_seconds"] > 0, f"{label} timeout drift")
    tool_keys = {"role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"}
    for role in ("cargo", "rustc", "uv", "python"):
        tool = value.get(role)
        check(errors, isinstance(tool, dict) and set(tool) == tool_keys, f"{label}.{role} keys drift")
        if not isinstance(tool, dict):
            continue
        executable = tool.get("executable")
        check(errors, tool.get("role") == role, f"{label}.{role} role drift")
        check(errors, isinstance(executable, str) and executable and Path(executable).name == executable and "/" not in executable and "\\" not in executable, f"{label}.{role} executable drift")
        check(errors, tool.get("path_redacted") is True, f"{label}.{role} path disclosure")
        check(errors, isinstance(tool.get("file_sha256"), str) and HEX64.fullmatch(tool["file_sha256"]) is not None, f"{label}.{role} file digest drift")
        check(errors, tool.get("version_exit_code") == 0, f"{label}.{role} version exit drift")
        check(errors, isinstance(tool.get("version_output_sha256"), str) and HEX64.fullmatch(tool["version_output_sha256"]) is not None, f"{label}.{role} version digest drift")


def verify_build(value: Any, errors: list[str], label: str) -> None:
    allowed = {"exit_code", "stdout_sha256", "stderr_sha256", "binary_sha256", "binary_custody"}
    check(errors, isinstance(value, dict) and set(value) == allowed, f"{label} keys drift")
    if not isinstance(value, dict):
        return
    check(errors, isinstance(value.get("exit_code"), int), f"{label} exit type drift")
    for key in ("stdout_sha256", "stderr_sha256"):
        check(errors, isinstance(value.get(key), str) and HEX64.fullmatch(value[key]) is not None, f"{label}.{key} digest drift")
    if value.get("exit_code") == 0:
        check(errors, isinstance(value.get("binary_sha256"), str) and HEX64.fullmatch(value["binary_sha256"]) is not None, f"{label}.binary_sha256 missing after successful build")
        check(errors, not validate_windows_pe_replay_custody(value.get("binary_custody")), f"{label}.binary_custody schema drift")
    elif value.get("binary_custody") is not None:
        check(errors, not validate_windows_pe_replay_custody(value.get("binary_custody")), f"{label}.binary_custody failed-build drift")
    if isinstance(value.get("binary_custody"), dict):
        check(errors, value.get("binary_sha256") == value["binary_custody"].get("raw_sha256"), f"{label}.raw binary/custody digest split")
    if value.get("binary_sha256") is not None:
        check(errors, isinstance(value["binary_sha256"], str) and HEX64.fullmatch(value["binary_sha256"]) is not None, f"{label}.binary_sha256 drift")


def verify_identity(report: dict[str, Any], errors: list[str], label: str) -> None:
    expected_candidate = {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive_sha256": CANDIDATE_ARCHIVE_SHA256}
    expected_upstream = {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "archive_sha256": UPSTREAM_ARCHIVE_SHA256}
    check(errors, report.get("candidate") == expected_candidate, f"{label} candidate identity drift")
    check(errors, report.get("upstream") == expected_upstream, f"{label} upstream identity drift")
    fixture = report.get("fixture")
    check(errors, isinstance(fixture, dict), f"{label} fixture missing")
    if isinstance(fixture, dict):
        check(errors, fixture.get("path") == "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml", f"{label} fixture path drift")
        check(errors, fixture.get("archive_present") is True, f"{label} fixture archive gate drift")
        check(errors, fixture.get("sha256") == FIXTURE_SHA256, f"{label} fixture digest drift")
        check(errors, fixture.get("source") == "candidate_archive", f"{label} fixture source drift")
        check(errors, fixture.get("archive_source_sha256") == FIXTURE_SHA256, f"{label} fixture source digest drift")


def derive_duo_contract(document: dict[str, Any], root: Path, errors: list[str]) -> dict[str, Any] | None:
    """Derive the PAM4/Duo partial status from both real replay reports."""
    corpus = document.get("corpus")
    report_specs = corpus.get("reports") if isinstance(corpus, dict) else None
    if not isinstance(report_specs, list) or len(report_specs) != 2:
        errors.append("Duo partial contract requires two replay reports")
        return None
    observed: list[dict[str, Any]] = []
    for index, spec in enumerate(report_specs):
        path_text = spec.get("path") if isinstance(spec, dict) else None
        if not isinstance(path_text, str):
            errors.append(f"Duo report {index} path is missing")
            continue
        try:
            report = json.loads((root / path_text).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"Duo report {index} cannot be loaded")
            continue
        cases = {item.get("id"): item for item in report.get("cases", []) if isinstance(item, dict)}
        values: dict[str, dict[str, Any]] = {}
        for case_id, modulation in (("pam4-noise-dfe", "pam4"), ("duo-noise-dfe", "duo")):
            case = cases.get(case_id)
            payload = case.get("payload") if isinstance(case, dict) else None
            fields = payload.get("compared_field_count") if isinstance(payload, dict) else None
            if not isinstance(fields, int) and isinstance(payload, dict) and isinstance(payload.get("fields"), list):
                fields = len(payload["fields"])
            values[modulation] = {"modulation": modulation, "case": case_id, "status": case.get("status") if isinstance(case, dict) else None, "fields": fields}
        observed.append(values)
    if len(observed) != 2:
        return None
    if observed[0] != observed[1]:
        errors.append("Duo partial report status/field count drift")
        return None
    expected = observed[0]
    if expected["pam4"]["status"] != "passed" or expected["duo"]["status"] != "blocked":
        errors.append("Duo partial contract is not PAM4-compared plus Duo-blocked")
    return {"status": "partial", "compared": expected["pam4"], "blocked": expected["duo"]}


def verify_report(report: dict[str, Any], errors: list[str], label: str, root: Path) -> None:
    check(errors, report.get("schema") == "sipi.pb-03-python-oracle-matrix-replay.v1", f"{label} schema drift")
    check(errors, report.get("row") == "PB-03", f"{label} row drift")
    check(errors, report.get("status") == "blocked", f"{label} status drift")
    check(errors, report.get("source_mode") == "git_archive_at_candidate_prep_commit_plus_content_addressed_input_corpus_and_harness_snapshot", f"{label} source mode drift")
    check(errors, isinstance(report.get("run_id"), str) and bool(report["run_id"]), f"{label} run ID missing")
    check(errors, isinstance(report.get("fresh_run_nonce"), str) and HEX32.fullmatch(report.get("fresh_run_nonce", "")) is not None, f"{label} nonce drift")
    verify_identity(report, errors, label)
    corpus = report.get("corpus")
    check(errors, isinstance(corpus, dict), f"{label} corpus missing")
    if isinstance(corpus, dict):
        corpus_path = root / "docs/baselines/pb-03-python-oracle-corpus-d3154093.v1.json"
        check(errors, corpus.get("path") == corpus_path.relative_to(root).as_posix(), f"{label} corpus path drift")
        check(errors, corpus.get("sha256") == digest(corpus_path), f"{label} corpus digest drift")
        check(errors, corpus.get("case_count") == len(CORPUS_CASES), f"{label} corpus count drift")
    harness = report.get("harness")
    check(errors, isinstance(harness, dict) and set(harness) == {"python_oracle", "runner"}, f"{label} harness keys drift")
    if isinstance(harness, dict):
        for key, path_text in (("python_oracle", "tools/pb_03_python_oracle.py"), ("runner", "tools/run_pb_03_python_oracle_matrix.py")):
            item = harness.get(key)
            check(errors, isinstance(item, dict) and item.get("path") == path_text, f"{label} harness {key} path drift")
            if isinstance(item, dict):
                allowed = {"path", "sha256", "snapshot"} if key == "python_oracle" else {"path", "sha256"}
                check(errors, set(item) == allowed, f"{label} harness {key} keys drift")
                check(errors, item.get("sha256") == digest(root / path_text), f"{label} harness {key} digest drift")
                check(errors, item.get("snapshot") == "candidate_prep_archive_harness_snapshot", f"{label} harness {key} snapshot drift")
    verify_build(report.get("build"), errors, f"{label} build")
    verify_toolchain(report.get("toolchain"), errors, f"{label} toolchain")
    cases = report.get("cases")
    check(errors, isinstance(cases, list) and {item.get("id") for item in cases if isinstance(item, dict)} == set(CORPUS_CASES), f"{label} case matrix drift")
    if isinstance(cases, list):
        for item in cases:
            if not isinstance(item, dict):
                continue
            check(errors, item.get("status") in {"passed", "blocked"}, f"{label} case status drift")
            check(errors, isinstance(item.get("blockers"), list), f"{label} case blockers missing")
    claims = report.get("claims")
    check(errors, isinstance(claims, dict) and claims.get("independent_python_payload_oracle") is True and claims.get("global_branch_parity") is False and claims.get("promotion") is False, f"{label} claims drift")
    check(errors, path_free(report), f"{label} contains an absolute path")


def verify_aggregate(aggregate: dict[str, Any], reports: list[dict[str, Any]], bindings: list[dict[str, Any]], errors: list[str], root: Path) -> None:
    check(errors, aggregate.get("schema") == "sipi.pb-03-python-oracle-matrix-aggregate.v1", "aggregate schema drift")
    check(errors, aggregate.get("row") == "PB-03" and aggregate.get("status") == "blocked", "aggregate row/status drift")
    check(errors, aggregate.get("source_mode") == "git_archive_at_candidate_prep_commit_plus_content_addressed_input_corpus_and_harness_snapshot", "aggregate source mode drift")
    check(errors, aggregate.get("reports") == bindings, "aggregate report binding drift")
    if reports:
        for key in ("candidate", "upstream", "fixture", "corpus", "harness", "toolchain"):
            check(errors, aggregate.get(key) == reports[0].get(key), f"aggregate {key} drift")
    check(errors, aggregate.get("manifest") == {"path": "docs/baselines/pb-03-python-oracle-18-branch-d3154093.v1.yaml", "binding_sha256": manifest_binding(yaml.safe_load((root / MANIFEST).read_text(encoding="utf-8")))}, "aggregate manifest binding drift")
    audit = aggregate.get("audit")
    check(errors, isinstance(audit, dict) and audit.get("path") == AUDIT_PATH and audit.get("sha256") == digest(root / AUDIT_PATH), "aggregate audit binding drift")
    distinct = aggregate.get("distinct_gate")
    check(errors, isinstance(distinct, dict), "aggregate distinct gate missing")
    if isinstance(distinct, dict):
        for key in ("unique_report_paths", "unique_report_sha256", "unique_run_ids", "unique_fresh_run_nonces", "exact_candidate_identity", "exact_upstream_identity", "exact_toolchain_identity"):
            check(errors, distinct.get(key) is True, f"aggregate {key} drift")
        check(errors, distinct.get("exact_binary_canonical_sha256") is True, "aggregate canonical PE reproducibility gate drift")
    if len(reports) == 2:
        first_custody = reports[0].get("build", {}).get("binary_custody") if isinstance(reports[0].get("build"), dict) else None
        second_custody = reports[1].get("build", {}).get("binary_custody") if isinstance(reports[1].get("build"), dict) else None
        check(errors, not compare_windows_pe_custody(first_custody, second_custody), "aggregate PE custody gate drift")
        expected_builds = [
            {
                "report": binding["path"],
                "binary_sha256": report.get("build", {}).get("binary_sha256"),
                "binary_custody": report.get("build", {}).get("binary_custody"),
            }
            for binding, report in zip(bindings, reports)
        ]
        check(errors, aggregate.get("builds") == expected_builds, "aggregate binary custody binding drift")
        custody_gate = aggregate.get("binary_custody_gate")
        check(errors, isinstance(custody_gate, dict), "aggregate PE custody gate missing")
        if isinstance(custody_gate, dict):
            check(errors, set(custody_gate) == {"raw_sha256_equal", "canonical_sha256_equal", "normalization_shape_equal", "repro_policy", "blockers"}, "aggregate PE custody gate keys drift")
            check(errors, custody_gate.get("raw_sha256_equal") == (reports[0].get("build", {}).get("binary_sha256") == reports[1].get("build", {}).get("binary_sha256")), "aggregate raw PE gate drift")
            check(errors, custody_gate.get("canonical_sha256_equal") == (isinstance(first_custody, dict) and isinstance(second_custody, dict) and first_custody.get("canonical_sha256") == second_custody.get("canonical_sha256")), "aggregate canonical PE gate drift")
            check(errors, custody_gate.get("normalization_shape_equal") == (windows_pe_custody_shape(first_custody) == windows_pe_custody_shape(second_custody)), "aggregate PE normalization gate drift")
            check(errors, custody_gate.get("repro_policy") == windows_pe_repro_policy(first_custody, second_custody), "aggregate REPRO policy drift")
            check(errors, custody_gate.get("blockers") == compare_windows_pe_custody(first_custody, second_custody), "aggregate PE gate blocker drift")
    check(errors, path_free(aggregate), "aggregate contains an absolute path")

def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    check(errors, document.get("schema") == "sipi.pb-03-python-oracle-18-branch-d3154093.v1", "schema drift")
    check(errors, document.get("row") == "PB-03", "row drift")
    check(errors, document.get("status") == "branch_payload_oracle_open", "manifest must remain open")
    source = document.get("source")
    check(errors, isinstance(source, dict), "source missing")
    if isinstance(source, dict):
        check(errors, source.get("upstream_commit") == UPSTREAM_COMMIT, "upstream commit drift")
        check(errors, source.get("upstream_tree") == UPSTREAM_TREE, "upstream tree drift")
        check(errors, source.get("candidate_commit") == CANDIDATE_COMMIT, "candidate commit drift")
        check(errors, source.get("candidate_tree") == CANDIDATE_TREE, "candidate tree drift")
        check(errors, source.get("upstream_archive_sha256") == UPSTREAM_ARCHIVE_SHA256, "upstream archive drift")
        check(errors, source.get("candidate_archive_sha256") == CANDIDATE_ARCHIVE_SHA256, "candidate archive drift")
        check(errors, source.get("candidate_basis") == "immutable_candidate_commit", "candidate basis drift")
    branches = document.get("branch_inventory")
    check(errors, isinstance(branches, list) and len(branches) == 18, "18-branch inventory missing")
    duo_contract = derive_duo_contract(document, root, errors)
    if isinstance(branches, list):
        ids = [item.get("id") for item in branches if isinstance(item, dict)]
        check(errors, set(ids) == BRANCH_IDS and len(ids) == len(set(ids)), "branch IDs drift")
        for index, item in enumerate(branches):
            check(errors, isinstance(item, dict), f"branch {index} is not an object")
            if isinstance(item, dict):
                check(errors, item.get("rust_probe") in {"exercised", "external_blocked", "bounded_data_projection_only"}, f"branch {index} probe status invalid")
                check(errors, "oracle" in item, f"branch {index} oracle status missing")
                oracle = item.get("oracle")
                if isinstance(oracle, str):
                    check(errors, oracle in {"not_applicable_configuration_parser", "not_yet_payload_bound", "external_blocked"}, f"branch {index} oracle status invalid")
                elif isinstance(oracle, dict):
                    check(errors, oracle.get("status") in {"payload_compared", "payload_mismatch", "partial", "not_yet_payload_bound", "external_blocked"}, f"branch {index} oracle result invalid")
                    if item.get("id") == "legacy.modulation.pam4_duo_binary":
                        check(errors, duo_contract is not None and oracle == duo_contract, f"branch {index} Duo oracle must be an observed partial contract")
                else:
                    errors.append(f"branch {index} oracle result is not typed")
    check(errors, document.get("portable_branch_probe_missing") == [], "portable probe missing is nonempty")
    missing = document.get("python_payload_oracle_missing")
    check(errors, isinstance(missing, list) and bool(missing), "payload oracle scope was overstated")
    if isinstance(missing, list) and isinstance(branches, list):
        branch_by_id = {item.get("id"): item for item in branches if isinstance(item, dict)}
        check(errors, set(missing).issubset(BRANCH_IDS), "payload oracle missing contains unknown branch")
        for branch_id in missing:
            item = branch_by_id.get(branch_id)
            oracle = item.get("oracle") if isinstance(item, dict) else None
            status = oracle.get("status") if isinstance(oracle, dict) else oracle
            check(errors, status == "not_yet_payload_bound", f"payload oracle missing status drift: {branch_id}")
    claims = document.get("claims")
    check(errors, isinstance(claims, dict), "claims missing")
    if isinstance(claims, dict):
        check(errors, claims.get("independent_python_payload_oracle") is True, "independent oracle claim missing")
        check(errors, claims.get("eighteen_branch_inventory") is True, "18-branch claim missing")
        check(errors, claims.get("python_payload_parity_complete") is False, "payload parity was falsely closed")
        check(errors, claims.get("global_branch_parity") is False, "global parity was falsely closed")
        check(errors, claims.get("promotion") is False, "promotion claim drift")
    corpus = document.get("corpus")
    check(errors, isinstance(corpus, dict) and corpus.get("path") == "docs/baselines/pb-03-python-oracle-corpus-d3154093.v1.json", "corpus binding drift")
    if isinstance(corpus, dict):
        corpus_path = root / corpus["path"]
        check(errors, corpus_path.is_file(), "corpus missing")
        if corpus_path.is_file():
            check(errors, digest(corpus_path) == corpus.get("sha256"), "corpus digest drift")
        check(errors, corpus.get("cases") == CORPUS_CASES, "corpus case binding drift")
        report_bindings: list[dict[str, Any]] = []
        reports: list[dict[str, Any]] = []
        report_specs = corpus.get("reports")
        check(errors, isinstance(report_specs, list) and len(report_specs) == 2, "report bindings are incomplete")
        for index, report_spec in enumerate(report_specs if isinstance(report_specs, list) else []):
            if not isinstance(report_spec, dict):
                errors.append(f"report binding {index} is not an object")
                continue
            path_text = report_spec.get("path")
            check(errors, path_text in REPORT_PATHS, f"report binding {index} path drift")
            if not isinstance(path_text, str) or path_text not in REPORT_PATHS:
                continue
            report_path = root / path_text
            report, report_sha = load_json(report_path, errors, f"report {index}")
            if report is None:
                continue
            verify_report(report, errors, f"report {index}", root)
            reports.append(report)
            expected_binding = {
                "path": path_text,
                "sha256": report_sha,
                "run_id": report.get("run_id"),
                "fresh_run_nonce": report.get("fresh_run_nonce"),
            }
            check(errors, report_spec == expected_binding, f"report binding {index} is not content-addressed")
            report_bindings.append(expected_binding)
        check(errors, len(reports) == 2 and len(report_bindings) == 2, "two reports are required")
        if len(reports) == 2:
            check(errors, reports[0].get("run_id") != reports[1].get("run_id"), "report run IDs are not distinct")
            check(errors, reports[0].get("fresh_run_nonce") != reports[1].get("fresh_run_nonce"), "report nonces are not distinct")
            check(errors, report_bindings[0].get("sha256") != report_bindings[1].get("sha256"), "report digests are not distinct")
            for key in ("candidate", "upstream", "fixture", "corpus", "harness", "toolchain"):
                check(errors, reports[0].get(key) == reports[1].get(key), f"reports {key} identity drift")
        aggregate_spec = corpus.get("aggregate")
        check(errors, isinstance(aggregate_spec, dict), "aggregate binding missing")
        aggregate: dict[str, Any] | None = None
        if isinstance(aggregate_spec, dict):
            check(errors, aggregate_spec.get("path") == AGGREGATE_PATH, "aggregate path drift")
            aggregate_path = root / AGGREGATE_PATH
            aggregate, aggregate_sha = load_json(aggregate_path, errors, "aggregate")
            check(errors, aggregate_spec.get("sha256") == aggregate_sha, "aggregate digest drift")
            if aggregate is not None:
                verify_aggregate(aggregate, reports, report_bindings, errors, root)
    harness = document.get("harness")
    check(errors, isinstance(harness, dict), "harness missing")
    if isinstance(harness, dict):
        expected_harness = {
            "oracle": "tools/pb_03_python_oracle.py",
            "runner": "tools/run_pb_03_python_oracle_matrix.py",
            "verifier": "tools/verify_pb_03_python_oracle_matrix.py",
            "mutation_tests": "tools/test_verify_pb_03_python_oracle_matrix.py",
            "aggregator": "tools/aggregate_pb_03_python_oracle_matrix.py",
            "eighteen_branch_verifier": "tools/verify_pb_03_python_oracle_18_branch.py",
            "eighteen_branch_mutation_tests": "tools/test_verify_pb_03_python_oracle_18_branch.py",
        }
        check(errors, set(harness) == set(expected_harness), "harness inventory drift")
        for name, binding in harness.items():
            check(errors, isinstance(binding, dict), f"harness {name} missing")
            if isinstance(binding, dict):
                path = binding.get("path")
                check(errors, isinstance(path, str) and not Path(path).is_absolute() and ".." not in Path(path).parts, f"harness {name} path drift")
                if isinstance(path, str) and (root / path).is_file():
                    check(errors, HEX64.fullmatch(binding.get("sha256", "")) is not None, f"harness {name} digest malformed")
                    check(errors, digest(root / path) == binding.get("sha256"), f"harness {name} digest drift")
                if name in expected_harness:
                    check(errors, path == expected_harness[name], f"harness {name} path binding drift")
    audit = document.get("audit")
    check(errors, isinstance(audit, dict), "audit binding missing")
    if isinstance(audit, dict):
        check(errors, audit.get("path") == AUDIT_PATH, "audit path drift")
        audit_path = root / AUDIT_PATH
        check(errors, audit.get("sha256") == digest(audit_path), "audit digest drift")
        try:
            check(errors, path_free(audit_path.read_text(encoding="utf-8")), "audit contains an absolute path")
        except OSError:
            errors.append("audit missing")
    return {"valid": not errors, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
        result = verify(document, args.manifest.resolve().parents[2])
    except (OSError, ValueError, yaml.YAMLError, TypeError) as error:
        result = {"valid": False, "errors": [type(error).__name__]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
