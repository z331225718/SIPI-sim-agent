"""Hard gate for the AS-03 6b8dacb4 governing-corpus observation."""

from __future__ import annotations

import hashlib
import ast
import importlib.util
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/as-03-fit-yparam-numeric-bound-current-6b8dacb4.v1.yaml"
CANDIDATE = {"commit": "6b8dacb434c1b95571b45e0f07a15fe2e997b012", "tree": "5cf877e3da35f387f0a720a081c87214a2d6ca2b", "archive_sha256": "59becc6fbfede8dce7019ec1e57c7b8fb98c4682eb85894176050740e6df6cc4"}
UPSTREAM = {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "archive_sha256": "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144"}
UPSTREAM_ROOT = Path(r"C:\Users\z3312\code\agent-spice")
RUNNER_PATH = "tools/run_as_02_03_numeric_bound_v3.py"
AGGREGATOR_PATH = "tools/aggregate_as_02_03_numeric_bound_v3.py"
VERIFIER_PATH = "tools/verify_as_03_numeric_bound_current_6b8dacb4.py"
MUTATION_PATH = "tools/test_verify_as_03_numeric_bound_current_6b8dacb4.py"
RUNNER_SHA = "11fb2258679fbed702d7e0a12af447710eb4e294a1b5965b37c54f021f46729e"
AGGREGATOR_SHA = "36f7e9ba5bd8fbcad6542a4d8f0053a293fe16137058652ef081c1650a2b09ce"
MUTATION_SHA = "8f284eea40ebc208ec4db73beb467fbbc7a8edafae04445bb7784795967359df"
SOURCE_MAP_PATH = "docs/baselines/as-03-fit-yparam-source-map.v1.yaml"
SOURCE_MAP_SHA = "8b8b2a822690dcda4e2d711aaa0425bcb03bb ecca697ef0ac712ec444526e815".replace(" ", "")
NOTICE_PATH = "crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-03.md"
NOTICE_SHA = "0d8cdee1b93f8e8ea51df76653233fea5c8a8e3d5f32b15d276c23c0686b908a"
FIXTURE_SHA = "4da06c257a0f0108e4391d65f894b6bb0d62a24a8f00f82f0f0734e061f5de70"
AS03_ARGS = ["--n-poles-real", "1", "--n-poles-cmplx", "0", "--max-order", "1", "--fit-iterations", "2", "--max-y-rms-siemens", "100", "--passivity", "off"]
METRICS = {"candidate_snapshot": {"selected_order": 1, "target_met": True}, "candidate_y_mean_rms_siemens": 0.012928922397961246, "candidate_y_rms_siemens": 0.025857844795922492, "upstream_snapshot": {"target_met": True}, "upstream_y_mean_rms_siemens": 0.012928922397961241, "upstream_y_rms_siemens": 0.025857844795922482}
CUSTODY = {"archive_links_rejected": True, "archive_overlay": False, "create_new": True, "fresh_root": True, "offline_build": True, "path_redacted": True, "root_external_to_repository": True}
WRAPPER_POLICY = {"schema": "sipi.path-free-wrapper-policy.v1", "clear_inherited_rustc_wrapper": True, "clear_inherited_rustc_workspace_wrapper": True, "rustc_wrapper": "unset", "rustc_workspace_wrapper": "unset"}
REPORT_KEYS = {"build", "candidate", "custody", "execution", "fixture", "fixture_sha256", "fresh_run_nonce", "metrics", "non_claims", "numeric_parity", "parity_claim", "profile", "run_id", "runner", "schema", "status", "toolchain", "upstream", "workflow", "wrapper_policy"}
AGGREGATE_KEYS = {"blockers", "candidate", "custody", "custody_valid", "fixture", "metrics", "non_claims", "numeric_parity", "parity_claim", "profile", "reports", "runner", "schema", "status", "toolchain", "upstream", "workflow", "wrapper_policy"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
GIT_TIMEOUT_SECONDS = 300
GIT_OUTPUT_LIMIT = 256 * 1024 * 1024


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_env() -> dict[str, str]:
    environment = dict(__import__("os").environ)
    for key in tuple(environment):
        if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} or key.startswith("GIT_CONFIG_"):
            environment.pop(key, None)
    return environment


def _git_output(repository: Path, arguments: list[str]) -> bytes:
    # The archive SHA is part of the already-frozen reports; keep Git's archive
    # byte policy identical to the replay runner while still clearing ambient
    # repository/config injection through _git_env.
    command = ["git", "-C", str(repository), *arguments]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_git_env())
    try:
        output, error = process.communicate(timeout=GIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()
        raise RuntimeError("git command timed out") from exc
    if process.returncode != 0 or len(output) > GIT_OUTPUT_LIMIT or len(error) > 1024 * 1024:
        raise RuntimeError("git command failed or exceeded output budget")
    return output


def recompute_source_identity(repository: Path, commit: str) -> dict[str, str]:
    tree = _git_output(repository, ["show", "-s", "--format=%T", commit]).decode("ascii").strip()
    archive = _git_output(repository, ["archive", "--format=tar", commit])
    return {"commit": commit, "tree": tree, "archive_sha256": hashlib.sha256(archive).hexdigest()}


def manifest_core_sha(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(?ms)(^audit:\n  path: [^\n]+\n  sha256: )([0-9a-f]{64})$")
    normalized, count = pattern.subn(r"\1<AUDIT_SHA_ELIDED>", text, count=1)
    if count != 1:
        raise ValueError("audit hash line missing")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def has_absolute(value: object) -> bool:
    if isinstance(value, dict):
        return any(has_absolute(k) or has_absolute(v) for k, v in value.items())
    if isinstance(value, list):
        return any(has_absolute(v) for v in value)
    return isinstance(value, str) and bool(re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/)", value))


def repo_file(value: object, prefix: str) -> Path | None:
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    actual = ROOT / path
    return actual if actual.is_file() else None


def finite(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def legacy_profile_matches(path: Path) -> bool:
    try:
        source = path.read_bytes()
        tree = ast.parse(source.decode("utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return False
    fixture = None
    args = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "FIXTURE" for target in node.targets):
            try:
                fixture = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "args" for target in node.targets) and isinstance(node.value, ast.List):
            values = [item.value for item in node.value.elts if isinstance(item, ast.Constant)]
            if values[:2] == ["--n-poles-real", "1"]:
                args = values
    return isinstance(fixture, str) and hashlib.sha256(fixture.encode("ascii")).hexdigest() == FIXTURE_SHA and args == AS03_ARGS


def valid_tool(item: object, role: str) -> bool:
    keys = {"schema", "role", "executable", "path_redacted", "file_sha256", "version_sha256", "exit_code", "pre", "post", "pre_post_equal"}
    if not isinstance(item, dict) or set(item) != keys:
        return False
    if item.get("schema") != "sipi.path-free-tool-identity.v1" or item.get("role") != role or item.get("path_redacted") is not True or item.get("executable") != f"{role}.exe" or item.get("exit_code") != 0 or item.get("pre_post_equal") is not True:
        return False
    nested_keys = {"schema", "role", "executable", "path_redacted", "file_sha256", "version_sha256", "exit_code"}
    for key in ("pre", "post"):
        nested = item.get(key)
        if not isinstance(nested, dict) or set(nested) != nested_keys or nested.get("schema") != item["schema"] or nested.get("role") != role or nested.get("executable") != item["executable"] or nested.get("path_redacted") is not True or nested.get("exit_code") != 0 or not HEX64.fullmatch(nested.get("file_sha256", "")) or not HEX64.fullmatch(nested.get("version_sha256", "")):
            return False
    return item["pre"] == item["post"] and item["file_sha256"] == item["pre"]["file_sha256"] and item["version_sha256"] == item["pre"]["version_sha256"]


def valid_report(report: object, expected_sha: str) -> list[str]:
    if not isinstance(report, dict):
        return ["report object"]
    blockers: list[str] = []
    if set(report) != REPORT_KEYS or has_absolute(report):
        blockers.append("report exact shape/path")
    if report.get("schema") != "sipi.agent-spice-as-numeric-bound.v3" or report.get("workflow") != "AS-03" or report.get("status") != "completed_numeric_mismatch_open" or report.get("parity_claim") is not False or report.get("numeric_parity") is not False:
        blockers.append("report status")
    if report.get("candidate") != CANDIDATE or report.get("upstream") != UPSTREAM:
        blockers.append("report source")
    if report.get("runner") != {"repo_relative_path": RUNNER_PATH, "sha256": RUNNER_SHA}:
        blockers.append("report runner")
    if report.get("custody") != CUSTODY or report.get("profile") != {"fixture_sha256": FIXTURE_SHA, "as03_args": AS03_ARGS, "as03_profile": "governing_v2_v3_current_exact_fixture_and_args"}:
        blockers.append("report custody/profile")
    if report.get("wrapper_policy") != WRAPPER_POLICY:
        blockers.append("report wrapper policy")
    if report.get("fixture") != {"kind": "fixed_touchstone_line_s2p_v1", "generated_by_runner_constant": "tools/run_as_02_03_numeric_bound_v3.py:FIXTURE", "sha256": FIXTURE_SHA} or report.get("fixture_sha256") != FIXTURE_SHA:
        blockers.append("report fixture")
    if not isinstance(report.get("run_id"), str) or not report["run_id"] or not HEX64.fullmatch(report.get("fresh_run_nonce", "")):
        blockers.append("report fresh identity")
    if report.get("metrics") != METRICS or any(not finite(report["metrics"].get(key)) for key in ("candidate_y_mean_rms_siemens", "candidate_y_rms_siemens", "upstream_y_mean_rms_siemens", "upstream_y_rms_siemens")):
        blockers.append("report exact metrics")
    build = report.get("build")
    if not isinstance(build, dict) or set(build) != {"binary_sha256", "returncode", "stderr_bytes", "stderr_sha256", "stdout_bytes", "stdout_sha256"} or build.get("returncode") != 0 or not HEX64.fullmatch(build.get("binary_sha256", "")) or any(type(build.get(key)) is not int or build[key] < 0 for key in ("stderr_bytes", "stdout_bytes")) or not HEX64.fullmatch(build.get("stderr_sha256", "")) or not HEX64.fullmatch(build.get("stdout_sha256", "")):
        blockers.append("report build contract")
    execution = report.get("execution")
    if not isinstance(execution, dict) or set(execution) != {"candidate", "candidate_report_sha256", "upstream", "upstream_report_sha256"} or not HEX64.fullmatch(execution.get("candidate_report_sha256", "")) or not HEX64.fullmatch(execution.get("upstream_report_sha256", "")):
        blockers.append("report execution contract")
    elif any(not isinstance(execution.get(key), dict) or set(execution[key]) != {"returncode", "stderr_bytes", "stderr_sha256", "stdout_bytes", "stdout_sha256"} or execution[key].get("returncode") != 0 or any(type(execution[key].get(number)) is not int or execution[key][number] < 0 for number in ("stderr_bytes", "stdout_bytes")) or not HEX64.fullmatch(execution[key].get("stderr_sha256", "")) or not HEX64.fullmatch(execution[key].get("stdout_sha256", "")) for key in ("candidate", "upstream")):
        blockers.append("report execution contract")
    if report.get("non_claims") != ["Numeric mismatch remains open.", "No parity or acceptance tolerance is claimed.", "No SI-channel S-parameter fitting is claimed.", "No product or release promotion is claimed."]:
        blockers.append("report nonclaims")
    if not isinstance(report.get("toolchain"), dict) or set(report["toolchain"]) != {"cargo", "rustc", "python"} or any(not valid_tool(report["toolchain"].get(role), role) for role in ("cargo", "rustc", "python")):
        blockers.append("report toolchain")
    if not isinstance(expected_sha, str) or not HEX64.fullmatch(expected_sha):
        blockers.append("report hash")
    return blockers


def verify(path: Path = MANIFEST, document: dict[str, Any] | None = None) -> dict[str, Any]:
    if document is not None:
        doc = document
    else:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, TypeError, ValueError, yaml.YAMLError):
            return {"valid": False, "blockers": ["manifest malformed"]}
    blockers: list[str] = []
    expected_manifest_keys = {"aggregate", "audit", "comparison", "fixture", "global_row_closed", "harness", "legacy_v2_evidence", "non_claims", "numeric_parity", "parity_claim", "provenance", "reports", "schema", "source", "status"}
    if not isinstance(doc, dict) or set(doc) != expected_manifest_keys or has_absolute(doc):
        return {"valid": False, "blockers": ["manifest exact shape/path"]}
    if doc.get("schema") != "sipi.as-03-fit-yparam-numeric-bound-current.v1" or doc.get("status") != "governing_corpus_observation_open" or doc.get("parity_claim") is not False or doc.get("numeric_parity") is not False or doc.get("global_row_closed") is not False:
        blockers.append("manifest status")
    legacy = doc.get("legacy_v2_evidence")
    expected_legacy = {"manifest": {"path": "docs/baselines/as-03-fit-yparam-numeric-bound-v2.yaml", "sha256": "0ce8d64e0fa3dd8ec31a9073b0127782826106c641261984afc5932b50f669aa"}, "aggregate": {"path": "docs/baselines/as-03-numeric-bound-v2-aggregate.json", "sha256": "730b7a34bef04be54be8fe76138cd3d7c07fae8602ee106daab1d0784f50aeb2"}, "runner": {"path": "tools/run_as_02_03_numeric_bound_v2.py", "sha256": "dc5d52a6ee00c634d1a203dfb6af117cc5b3e25b5c8cdc2133ef383c09aa0bcc", "bytes": 9881}, "fixture_sha256": FIXTURE_SHA, "as03_args": [*AS03_ARGS[:-1], False], "metrics": {"candidate_y_rms_siemens": 0.04390770265061283, "upstream_y_rms_siemens": 0.02585784479592245, "candidate_y_mean_rms_siemens": 0.021953851325306414, "upstream_y_mean_rms_siemens": 0.012928922397961225}}
    if legacy != expected_legacy:
        blockers.append("legacy v2 evidence shape")
    for item, prefix in ((legacy.get("manifest", {}) if isinstance(legacy, dict) else {}, "docs/"), (legacy.get("aggregate", {}) if isinstance(legacy, dict) else {}, "docs/"), (legacy.get("runner", {}) if isinstance(legacy, dict) else {}, "tools/")):
        actual = repo_file(item.get("path"), prefix) if isinstance(item, dict) else None
        if actual is None or item.get("sha256") != sha(actual) or ("bytes" in item and item["bytes"] != actual.stat().st_size):
            blockers.append("legacy v2 physical binding")
    legacy_runner = repo_file(expected_legacy["runner"]["path"], "tools/")
    if legacy_runner is None or not legacy_profile_matches(legacy_runner):
        blockers.append("legacy v2 fixture/profile equivalence")
    legacy_aggregate = repo_file(expected_legacy["aggregate"]["path"], "docs/")
    if legacy_aggregate is None:
        blockers.append("legacy v2 aggregate missing")
    else:
        try:
            legacy_value = json.loads(legacy_aggregate.read_text(encoding="utf-8"))
            legacy_metrics = expected_legacy["metrics"]
            if legacy_value.get("workflow") != "AS-03" or legacy_value.get("status") != "completed_numeric_mismatch_open" or legacy_value.get("parity_claim") is not False or legacy_value.get("numeric_parity") is not False or legacy_value.get("blockers") != [] or legacy_value.get("metrics") != legacy_metrics:
                blockers.append("legacy v2 metrics")
        except (OSError, json.JSONDecodeError, TypeError):
            blockers.append("legacy v2 aggregate malformed")
    source = doc.get("source", {})
    if source != {"candidate": CANDIDATE, "upstream": {**UPSTREAM, "license": "MIT"}, "materialization": {"candidate": "git_archive_clean_temporary_root", "upstream": "pinned_git_archive_clean_temporary_root", "overlay_current_worktree": False}}:
        blockers.append("manifest source")
    try:
        if recompute_source_identity(ROOT, CANDIDATE["commit"]) != CANDIDATE or recompute_source_identity(UPSTREAM_ROOT, UPSTREAM["commit"]) != UPSTREAM:
            blockers.append("source identity recomputation")
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError):
        blockers.append("source identity recomputation")
    if doc.get("fixture") != {"kind": "fixed_touchstone_line_s2p_v1", "generated_by_runner_constant": "tools/run_as_02_03_numeric_bound_v3.py:FIXTURE", "sha256": FIXTURE_SHA}:
        blockers.append("manifest fixture")
    for key, expected_path, expected_sha in (("runner", RUNNER_PATH, RUNNER_SHA), ("aggregator", AGGREGATOR_PATH, AGGREGATOR_SHA)):
        item = doc.get("harness", {}).get(key, {})
        actual = repo_file(item.get("path"), "tools/") if isinstance(item, dict) else None
        if item != {"path": expected_path, "sha256": expected_sha} or actual is None or sha(actual) != expected_sha:
            blockers.append(f"harness {key}")
    verifier_sha = sha(ROOT / VERIFIER_PATH)
    for key, expected_path, expected_sha in (("verifier", VERIFIER_PATH, verifier_sha), ("mutation_tests", MUTATION_PATH, MUTATION_SHA)):
        item = doc.get("harness", {}).get(key, {})
        actual = repo_file(item.get("path"), "tools/") if isinstance(item, dict) else None
        if item != {"path": expected_path, "sha256": expected_sha} or actual is None or sha(actual) != expected_sha:
            blockers.append(f"harness {key}")
    for key, expected_path, expected_sha, prefix in (("source_map", SOURCE_MAP_PATH, SOURCE_MAP_SHA, "docs/"), ("notice", NOTICE_PATH, NOTICE_SHA, "crates/")):
        item = doc.get("provenance", {}).get(key, {})
        actual = repo_file(item.get("path"), prefix) if isinstance(item, dict) else None
        if item != {"path": expected_path, "sha256": expected_sha} or actual is None or sha(actual) != expected_sha:
            blockers.append(f"provenance {key}")
    report_items = doc.get("reports")
    expected_reports = [
        {"path": "docs/baselines/as-03-numeric-bound-current-6b8dacb4-run-01.json", "sha256": "bca4296f296fe89740f2e526f1a301f688a55699af0a1f889e781e1ce3ae9df3", "run_id": "as03-6b8dacb4-fresh-01", "fresh_run_nonce": "d2701aec1dea54237ac26687a4923f43903c6cd57711651a2de9ba08fb9d483f"},
        {"path": "docs/baselines/as-03-numeric-bound-current-6b8dacb4-run-02.json", "sha256": "f598d5f9ed284f0e8eac79b39eb7d71c7d61e44462e6087b5560d06bfc895b80", "run_id": "as03-6b8dacb4-fresh-02", "fresh_run_nonce": "ca89b480432044e0813fb9450cf887e9e983bb263ff04f626314ce25fc5797f0"},
    ]
    if report_items != expected_reports:
        blockers.append("manifest reports")
        report_items = expected_reports
    reports: list[dict[str, Any]] = []
    for item in report_items:
        actual = repo_file(item["path"], "docs/")
        if actual is None or sha(actual) != item["sha256"]:
            blockers.append("report physical hash")
            continue
        try:
            report = json.loads(actual.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
            blockers.append("report malformed")
            continue
        blockers.extend(valid_report(report, item["sha256"]))
        if report.get("run_id") != item["run_id"] or report.get("fresh_run_nonce") != item["fresh_run_nonce"]:
            blockers.append("report manifest identity")
        reports.append(report)
    if len(reports) == 2 and reports[0] == reports[1]:
        blockers.append("fresh reports identical")
    if len(reports) == 2:
        for key in ("candidate", "upstream", "runner", "wrapper_policy", "custody", "profile", "fixture", "fixture_sha256", "toolchain", "metrics"):
            if reports[0].get(key) != reports[1].get(key):
                blockers.append(f"cross-run drift:{key}")
        if reports[0].get("run_id") == reports[1].get("run_id") or reports[0].get("fresh_run_nonce") == reports[1].get("fresh_run_nonce"):
            blockers.append("cross-run fresh identity")
    aggregate = doc.get("aggregate", {})
    aggregate_path = "docs/baselines/as-03-numeric-bound-current-6b8dacb4-aggregate.json"
    aggregate_sha = "49f78eff9f04bf522fb0b2a32119952e2529a6b4ef0a605e7945b852e03260a8"
    if aggregate != {"path": aggregate_path, "sha256": aggregate_sha}:
        blockers.append("manifest aggregate")
    aggregate_file = repo_file(aggregate_path, "docs/")
    aggregate_value: dict[str, Any] | None = None
    if aggregate_file is None or sha(aggregate_file) != aggregate_sha:
        blockers.append("aggregate physical hash")
    else:
        try:
            loaded_aggregate = json.loads(aggregate_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
            blockers.append("aggregate malformed")
        else:
            if isinstance(loaded_aggregate, dict):
                aggregate_value = loaded_aggregate
                expected_bindings = [{"path": item["path"], "sha256": item["sha256"], "run_id": item["run_id"], "fresh_run_nonce": item["fresh_run_nonce"]} for item in expected_reports]
                if set(aggregate_value) != AGGREGATE_KEYS or has_absolute(aggregate_value) or aggregate_value.get("schema") != "sipi.agent-spice-as-numeric-bound-aggregate.v3" or aggregate_value.get("workflow") != "AS-03" or aggregate_value.get("status") != "completed_numeric_mismatch_open" or aggregate_value.get("custody_valid") is not True or aggregate_value.get("parity_claim") is not False or aggregate_value.get("numeric_parity") is not False or aggregate_value.get("blockers") != [] or aggregate_value.get("reports") != expected_bindings or aggregate_value.get("candidate") != CANDIDATE or aggregate_value.get("upstream") != UPSTREAM or aggregate_value.get("runner") != {"repo_relative_path": RUNNER_PATH, "sha256": RUNNER_SHA} or aggregate_value.get("custody") != CUSTODY or aggregate_value.get("profile") != (reports[0].get("profile") if reports else None) or aggregate_value.get("toolchain") != (reports[0].get("toolchain") if reports else None) or aggregate_value.get("wrapper_policy") != (reports[0].get("wrapper_policy") if reports else None) or aggregate_value.get("metrics") != METRICS or aggregate_value.get("non_claims") != ["Numeric mismatch remains open.", "No acceptance tolerance or product parity is claimed."]:
                    blockers.append("aggregate exact binding")
            else:
                blockers.append("aggregate object")
    if aggregate_value is not None and len(reports) == 2:
        try:
            spec = importlib.util.spec_from_file_location("as03_aggregate", ROOT / AGGREGATOR_PATH)
            if spec is None or spec.loader is None:
                raise RuntimeError("aggregator loader unavailable")
            aggregate_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(aggregate_module)

            with tempfile.TemporaryDirectory(dir=ROOT / "docs" / "baselines") as temporary:
                reproduced = Path(temporary) / "aggregate.json"
                aggregate_module.aggregate(ROOT / expected_reports[0]["path"], ROOT / expected_reports[1]["path"], reproduced)
                if reproduced.read_bytes() != aggregate_file.read_bytes():
                    blockers.append("aggregate regeneration")
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
            blockers.append("aggregate regeneration")
    comparison = doc.get("comparison")
    if comparison != {"legacy_v2_candidate_y_rms_siemens": 0.04390770265061283, "legacy_v2_upstream_y_rms_siemens": 0.02585784479592245, "current_candidate_y_rms_siemens": METRICS["candidate_y_rms_siemens"], "current_upstream_y_rms_siemens": METRICS["upstream_y_rms_siemens"], "large_legacy_mismatch_resolved": True, "remaining_numeric_mismatch_open": True}:
        blockers.append("comparison exact binding")
    audit = doc.get("audit", {})
    audit_path = "docs/baselines/audits/2026-08-24-as-03-numeric-bound-current-6b8dacb4.md"
    audit_file = repo_file(audit_path, "docs/")
    audit_sha = audit.get("sha256") if isinstance(audit, dict) else None
    try:
        audit_text = audit_file.read_text(encoding="utf-8") if audit_file is not None else ""
    except (OSError, UnicodeDecodeError):
        audit_text = ""
    try:
        current_manifest_core_sha = manifest_core_sha(path)
    except (OSError, UnicodeDecodeError, ValueError):
        current_manifest_core_sha = ""
    audit_anchors = (f"Current manifest path: `{MANIFEST.relative_to(ROOT).as_posix()}`; core SHA256: `{current_manifest_core_sha}`", f"Aggregate path: `{aggregate_path}`; SHA256: `{aggregate_sha}`", CANDIDATE["commit"], UPSTREAM["commit"], "docs/baselines/as-03-numeric-bound-current-6b8dacb4-run-01.json", "bca4296f296fe89740f2e526f1a301f688a55699af0a1f889e781e1ce3ae9df3", "docs/baselines/as-03-numeric-bound-current-6b8dacb4-run-02.json", "f598d5f9ed284f0e8eac79b39eb7d71c7d61e44462e6087b5560d06bfc895b80", RUNNER_PATH, RUNNER_SHA, AGGREGATOR_PATH, AGGREGATOR_SHA, VERIFIER_PATH, verifier_sha, MUTATION_PATH, "325d86ede6a66d72482b631c7ccc3368a2886853009cbf491b0c0237643200ae", SOURCE_MAP_PATH, SOURCE_MAP_SHA, NOTICE_PATH, NOTICE_SHA, "Legacy v2 manifest path: `docs/baselines/as-03-fit-yparam-numeric-bound-v2.yaml`; SHA256: `0ce8d64e0fa3dd8ec31a9073b0127782826106c641261984afc5932b50f669aa`", "Legacy v2 aggregate path: `docs/baselines/as-03-numeric-bound-v2-aggregate.json`; SHA256: `730b7a34bef04be54be8fe76138cd3d7c07fae8602ee106daab1d0784f50aeb2`", "same fixture bytes and AS-03 args", "global parity remains open")
    audit_anchors = tuple(anchor for anchor in audit_anchors if anchor != "325d86ede6a66d72482b631c7ccc3368a2886853009cbf491b0c0237643200ae") + (MUTATION_SHA,)
    if audit.get("path") != audit_path or audit_file is None or audit_sha != sha(audit_file) or any(anchor not in audit_text for anchor in audit_anchors):
        blockers.append("audit reciprocal binding")
    if doc.get("non_claims") != ["no_global_numeric_parity", "no_acceptance_tolerance", "no_si_channel_s_parameter_fit", "no_product_or_release_promotion", "no_release_promotion"]:
        blockers.append("manifest nonclaims")
    return {"valid": not blockers, "blockers": blockers}


if __name__ == "__main__":
    import sys

    result = verify(Path(sys.argv[1]) if len(sys.argv) > 1 else MANIFEST)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["valid"] else 1)
