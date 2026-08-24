"""Fail-closed verifier for the PB-03 ed7b12d2 scoped replay."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from pb_03_replay_common import validate_windows_pe_replay_custody


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = "docs/baselines/pb-03-direct-ed7b12d2-current.v1.yaml"
AUDIT_PATH = "docs/baselines/audits/2026-08-24-pb-03-ed7b12d2-current.json"
VERIFIER_PATH = "tools/verify_pb_03_direct_ed7b12d2_current.py"
MUTATION_TEST_PATH = "tools/test_verify_pb_03_direct_ed7b12d2_current.py"
AGGREGATE_TEST_PATH = "tools/test_aggregate_pb_03_scoped.py"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{32,64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")
CANDIDATE = {
    "commit": "ed7b12d22cd14c235236147055742dd208541635",
    "tree": "149e962a3e730b0d5ffbd76b06e4e291722d62a6",
    "archive_sha256": "54457eb7ac1aa2de61fa1fca6ed06121d7a9386352f2e6b6b1a90205a32a71db",
}
UPSTREAM = {
    "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
    "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
    "archive_sha256": "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25",
}
FIXTURE = {
    "path": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml",
    "bytes": 1170,
    "sha256": "2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f",
}
REPORTS = (
    {
        "path": "docs/baselines/pb-03-direct-ed7b12d2-run-01.json",
        "sha256": "5113f55c4c0644e46611db3edad423804cd106864e6616cb383ee69a222aed8f",
        "run_id": "pb-03-ed7b12d2-formal-01",
        "fresh_run_nonce": "e454fd35e41c413db389a0c7e7a282ba",
    },
    {
        "path": "docs/baselines/pb-03-direct-ed7b12d2-run-02.json",
        "sha256": "b4bd16f3680828c45a1ec177111c1c62aa137926be09f3f732408017441775ca",
        "run_id": "pb-03-ed7b12d2-formal-02",
        "fresh_run_nonce": "30fcfcce25e94ee99a844bb447801a73",
    },
)
AGGREGATE = {
    "path": "docs/baselines/pb-03-direct-ed7b12d2-aggregate.json",
    "sha256": "c5f54a591c9ab5037545468e4872e4906a2388686ae4d99497bd193edc1c1d64",
}
STABLE_NAMES = (
    "ber_auto_correlation.npy", "ber_error_indices.npy", "ber_observed_bits.npy", "ber_reference_bits.npy",
    "channel_impulse_v_per_v.npy", "channel_output_v.npy", "ctle_output_v.npy", "dfe_bits.npy",
    "dfe_clock_times_s.npy", "dfe_clocks.npy", "dfe_decision_scalers_v.npy", "dfe_decisions.npy",
    "dfe_locked.npy", "dfe_output_v.npy", "dfe_signal_samples_v.npy", "dfe_tap_weights_v.npy",
    "dfe_ui_estimates_s.npy", "legacy_channel_frequency_hz.npy", "legacy_channel_raw_im.npy",
    "legacy_channel_raw_re.npy", "legacy_channel_terminated_im.npy", "legacy_channel_terminated_re.npy",
    "legacy_channel_trimmed_im.npy", "legacy_channel_trimmed_re.npy", "legacy_stage_ctle_im.npy",
    "legacy_stage_ctle_out_im.npy", "legacy_stage_ctle_out_re.npy", "legacy_stage_ctle_re.npy",
    "legacy_stage_dfe_im.npy", "legacy_stage_dfe_out_im.npy", "legacy_stage_dfe_out_re.npy",
    "legacy_stage_dfe_re.npy", "legacy_stage_tx_im.npy", "legacy_stage_tx_out_im.npy",
    "legacy_stage_tx_out_re.npy", "legacy_stage_tx_re.npy", "rx_ffe_impulse_v_per_v.npy",
    "rx_filter_impulse_v_per_v.npy", "rx_input_v.npy", "rx_output_v.npy", "symbols_v.npy", "time_s.npy",
    "tx_channel_impulse_v_per_v.npy", "tx_waveform_v.npy",
)
STABLE_SHA256 = "67e0fb568f1d0461e1b60c2b5cd3e52c5ade90bb689067740bff7d82d0fe02e7"
FIXED_NON_CLAIMS = (
    "This is one frozen fixture only.",
    "PB-03 payload parity is only the fixed stable array subset, not whole-payload parity.",
    "The candidate and oracle do not prove independent implementations.",
    "Uncovered branches, global parity, product capability, and release approval remain open.",
)
AGGREGATE_NON_CLAIMS = (
    "A frozen fixture does not cover all branches.",
    "This aggregate is not a license decision or release approval.",
)
EXPECTED_TOOLCHAIN = {
    "timeout_seconds": 1200,
    "cargo": {"role": "cargo", "executable": "cargo.EXE", "path_redacted": True, "file_sha256": "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7", "version_exit_code": 0, "version_output_sha256": "4e9216fb7cac2573c1a8d60be140200103a52ab9fd9415070d94a98b1ef5973a"},
    "rustc": {"role": "rustc", "executable": "rustc.EXE", "path_redacted": True, "file_sha256": "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7", "version_exit_code": 0, "version_output_sha256": "d6dec673ca010f6a7d90aa3f4a896ad9d88b66b8fe090296c298eddfe9a406db"},
    "uv": {"role": "uv", "executable": "uv.EXE", "path_redacted": True, "file_sha256": "5a7ec85884c2ccb1be560cb8fac3eb890df1adf49bfcc070a270ba70401bdd68", "version_exit_code": 0, "version_output_sha256": "ab0d29803cb58959acc6cf64650fb215c72c2989b94fb6f9de5f22814ceca82d"},
    "python": {"role": "python", "executable": "python.EXE", "path_redacted": True, "file_sha256": "ee3131591ecdc30ebc9221769239e9d89df47380ed01e1b25ba2c68f6e808417", "version_exit_code": 0, "version_output_sha256": "92f6867409cdf8c3f751b9944dd73439d19ddc74b01315c6cafb474011d2fa1e"},
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def repo_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def path_free(value: Any) -> bool:
    return PATH_LEAK.search(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)) is None


def load_json(relative: str, errors: list[str], label: str) -> tuple[dict[str, Any] | None, str | None]:
    if not repo_relative(relative):
        errors.append(f"{label} path is not repository-relative")
        return None, None
    path = ROOT / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        actual = digest(path)
    except (OSError, ValueError) as error:
        errors.append(f"{label} cannot be loaded: {error}")
        return None, None
    if not isinstance(value, dict):
        errors.append(f"{label} is not an object")
        return None, actual
    return value, actual


def check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def recompute_archive(repo: Path, commit: str) -> dict[str, str] | None:
    try:
        archive = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), "archive", "--format=tar", commit],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if archive.returncode != 0:
            return None
        resolved = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), "rev-parse", f"{commit}^{{commit}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        tree = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), "rev-parse", f"{commit}^{{tree}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if resolved.returncode != 0 or tree.returncode != 0:
            return None
        return {
            "commit": resolved.stdout.decode("ascii").strip(),
            "tree": tree.stdout.decode("ascii").strip(),
            "archive_sha256": hashlib.sha256(archive.stdout).hexdigest(),
        }
    except (OSError, UnicodeError):
        return None


def recompute_blob(repo: Path, commit: str, relative: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), "show", f"{commit}:{relative}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def verify_member_map(report: dict[str, Any], errors: list[str], label: str) -> str | None:
    replay = report.get("replay")
    artifact = replay.get("candidate_artifact") if isinstance(replay, dict) else None
    arrays = artifact.get("arrays") if isinstance(artifact, dict) else None
    members = arrays.get("logical_members") if isinstance(arrays, dict) else None
    check(errors, isinstance(members, dict), f"{label} stable array map missing")
    if not isinstance(members, dict):
        return None
    check(errors, set(members) == set(STABLE_NAMES), f"{label} stable array names drift")
    for name, member in members.items():
        if name not in STABLE_NAMES:
            continue
        check(errors, isinstance(member, dict), f"{label} member {name} is not an object")
        if not isinstance(member, dict):
            continue
        check(errors, set(member) == {"count", "dtype", "f64_sha256", "fortran_order", "shape"}, f"{label} member {name} schema drift")
        check(errors, member.get("dtype") == "<f8" and member.get("fortran_order") is False, f"{label} member {name} dtype drift")
        check(errors, isinstance(member.get("count"), int) and not isinstance(member.get("count"), bool) and member["count"] >= 0, f"{label} member {name} count drift")
        shape = member.get("shape")
        check(errors, isinstance(shape, list) and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in shape), f"{label} member {name} shape drift")
        if isinstance(shape, list) and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in shape):
            product = 1
            for item in shape:
                product *= item
            check(errors, product == member.get("count"), f"{label} member {name} count/shape mismatch")
        check(errors, isinstance(member.get("f64_sha256"), str) and HEX64.fullmatch(member["f64_sha256"]) is not None, f"{label} member {name} digest drift")
    stable = {name: members.get(name) for name in STABLE_NAMES}
    stable_digest = hashlib.sha256(canonical(stable)).hexdigest()
    check(errors, stable_digest == STABLE_SHA256, f"{label} stable array canonical digest drift")
    return stable_digest


def verify_report(report: dict[str, Any], expected: dict[str, str], errors: list[str], label: str) -> None:
    check(errors, set(report) == {"blockers", "build", "candidate", "claims", "custody", "fixture", "fresh_run_nonce", "non_claims", "replay", "row", "run_id", "schema", "source_mode", "status", "toolchain", "upstream"}, f"{label} top-level schema drift")
    check(errors, report.get("schema") == "sipi.pb-03-direct-replay.v1" and report.get("row") == "PB-03", f"{label} identity drift")
    check(errors, report.get("status") == "passed" and report.get("blockers") == [], f"{label} is not a clean pass")
    check(errors, report.get("source_mode") == "git_archive_at_immutable_commit", f"{label} source mode drift")
    check(errors, report.get("run_id") == expected["run_id"] and report.get("fresh_run_nonce") == expected["fresh_run_nonce"], f"{label} run binding drift")
    check(errors, isinstance(report.get("fresh_run_nonce"), str) and NONCE.fullmatch(report.get("fresh_run_nonce", "")) is not None, f"{label} nonce malformed")
    check(errors, report.get("candidate") == CANDIDATE and report.get("upstream") == UPSTREAM, f"{label} source archive drift")
    check(errors, report.get("fixture") == {**FIXTURE, "archive_present": True}, f"{label} fixture drift")
    check(errors, report.get("toolchain") == EXPECTED_TOOLCHAIN, f"{label} toolchain drift")
    build = report.get("build")
    check(errors, isinstance(build, dict) and set(build) == {"binary_custody", "binary_sha256", "exit_code", "stderr_sha256", "stdout_sha256"}, f"{label} build schema drift")
    if isinstance(build, dict):
        check(errors, build.get("exit_code") == 0, f"{label} build exit drift")
        for stream in ("stdout_sha256", "stderr_sha256"):
            check(errors, isinstance(build.get(stream), str) and HEX64.fullmatch(build.get(stream, "")) is not None, f"{label} {stream} drift")
        custody = build.get("binary_custody")
        check(errors, isinstance(custody, dict), f"{label} binary custody missing")
        if isinstance(custody, dict):
            check(errors, not validate_windows_pe_replay_custody(custody), f"{label} binary custody schema drift")
            check(errors, build.get("binary_sha256") == custody.get("raw_sha256"), f"{label} binary/raw SHA drift")
            check(errors, isinstance(build.get("binary_sha256"), str) and HEX64.fullmatch(build.get("binary_sha256", "")) is not None, f"{label} binary SHA drift")
    custody = report.get("custody")
    check(errors, custody == {"materialized_archives_created_new": True, "run_root_created_new": True, "work_root_created_new": True, "work_root_outside_candidate_repo": True, "work_root_outside_upstream_repo": True, "work_root_path_redacted": True}, f"{label} custody drift")
    claims = report.get("claims")
    check(errors, claims == {"global_row_closed": False, "independent_implementation": False, "payload_parity": True, "payload_scope": "fixed_pb03_stable_array_subset", "release_approval": False, "whole_payload_parity": False}, f"{label} claims drift")
    check(errors, report.get("non_claims") == list(FIXED_NON_CLAIMS), f"{label} non-claims drift")
    replay = report.get("replay")
    check(errors, isinstance(replay, dict) and set(replay) == {"candidate_artifact", "candidate_process", "comparison", "oracle_artifact", "oracle_process", "payload", "selection", "semantic_gate"}, f"{label} replay schema drift")
    if not isinstance(replay, dict):
        return
    payload = replay.get("payload")
    check(errors, payload == {"candidate_logical_sha256": STABLE_SHA256, "equal": True, "oracle_logical_sha256": STABLE_SHA256}, f"{label} payload drift")
    check(
        errors,
        replay.get("semantic_gate") is True
        and replay.get("selection") == {"candidate": None, "expected": None, "oracle": None}
        and replay.get("comparison") == {"candidate": None, "oracle": None, "payload_gate": None},
        f"{label} workflow semantics drift",
    )
    for side in ("candidate_process", "oracle_process"):
        process = replay.get(side)
        check(errors, isinstance(process, dict) and set(process) == {"exit_code", "stderr_sha256", "stdout_sha256"}, f"{label} {side} process schema drift")
        if isinstance(process, dict):
            check(errors, process.get("exit_code") == 0, f"{label} {side} exit drift")
            for key in ("stderr_sha256", "stdout_sha256"):
                check(errors, isinstance(process.get(key), str) and HEX64.fullmatch(process.get(key, "")) is not None, f"{label} {side} {key} drift")
    for side in ("candidate_artifact", "oracle_artifact"):
        artifact = replay.get(side)
        check(errors, isinstance(artifact, dict), f"{label} {side} artifact missing")
        if not isinstance(artifact, dict):
            continue
        check(errors, set(artifact) == {"arrays", "arrays_present", "comparison", "meta_json_valid", "meta_payload_sha256", "meta_present", "meta_schema", "meta_sha256", "selection"}, f"{label} {side} artifact schema drift")
        check(errors, artifact.get("meta_schema") == "pybert.native-cli-result.v1" and artifact.get("meta_present") is True and artifact.get("meta_json_valid") is True and artifact.get("arrays_present") is True, f"{label} {side} schema drift")
        check(errors, artifact.get("selection") is None and artifact.get("comparison") is None, f"{label} {side} workflow artifact semantics drift")
        arrays = artifact.get("arrays")
        check(errors, isinstance(arrays, dict) and set(arrays) == {"bytes", "logical_member_count", "logical_members", "logical_sha256", "sha256"}, f"{label} {side} arrays schema drift")
        if isinstance(arrays, dict):
            check(errors, isinstance(arrays.get("bytes"), int) and not isinstance(arrays.get("bytes"), bool) and arrays["bytes"] > 0, f"{label} {side} array bytes drift")
            check(errors, isinstance(arrays.get("logical_member_count"), int) and not isinstance(arrays.get("logical_member_count"), bool) and arrays["logical_member_count"] > 0, f"{label} {side} logical count drift")
            for key in ("logical_sha256", "sha256"):
                check(errors, isinstance(arrays.get(key), str) and HEX64.fullmatch(arrays.get(key, "")) is not None, f"{label} {side} array {key} drift")
        for key in ("meta_payload_sha256", "meta_sha256"):
            check(errors, isinstance(artifact.get(key), str) and HEX64.fullmatch(artifact.get(key, "")) is not None, f"{label} {side} {key} drift")
        verify_member_map({"replay": {"candidate_artifact": artifact}}, errors, f"{label} {side}")
    candidate_artifact = replay.get("candidate_artifact")
    oracle_artifact = replay.get("oracle_artifact")
    candidate_arrays = candidate_artifact.get("arrays", {}) if isinstance(candidate_artifact, dict) else {}
    oracle_arrays = oracle_artifact.get("arrays", {}) if isinstance(oracle_artifact, dict) else {}
    check(
        errors,
        isinstance(candidate_arrays, dict)
        and isinstance(oracle_arrays, dict)
        and candidate_arrays.get("logical_members") == oracle_arrays.get("logical_members"),
        f"{label} candidate/oracle stable array map drift",
    )


def verify(manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    expected_manifest_keys = {"audit", "claims", "evidence", "fixture", "harness", "inventory", "non_claims", "replay_policy", "row", "schema", "source", "status", "version"}
    check(errors, isinstance(manifest, dict) and set(manifest) == expected_manifest_keys, "manifest schema drift")
    if not isinstance(manifest, dict):
        return {"valid": False, "errors": errors}
    check(errors, manifest.get("schema") == "sipi.pb-03-ed7b12d2-current.v1" and manifest.get("version") == 1 and manifest.get("row") == "PB-03", "manifest identity drift")
    check(errors, manifest.get("status") == "passed_scoped_observation", "manifest status drift")
    check(errors, manifest.get("source") == {"candidate": CANDIDATE, "upstream": UPSTREAM}, "manifest source drift")
    candidate_source = recompute_archive(ROOT, CANDIDATE["commit"])
    upstream_source = recompute_archive(Path.home() / "code" / "Py-bert-agent", UPSTREAM["commit"])
    check(errors, candidate_source == CANDIDATE, "candidate archive recomputation drift")
    check(errors, upstream_source == UPSTREAM, "upstream archive recomputation drift")
    check(errors, manifest.get("fixture") == FIXTURE, "manifest fixture drift")
    fixture_path = ROOT / FIXTURE["path"]
    try:
        blob = recompute_blob(ROOT, CANDIDATE["commit"], FIXTURE["path"])
        check(errors, blob is not None and len(blob) == FIXTURE["bytes"] and hashlib.sha256(blob).hexdigest() == FIXTURE["sha256"], "candidate archive fixture bytes/hash drift")
        check(errors, fixture_path.is_file() and fixture_path.stat().st_size == FIXTURE["bytes"] and digest(fixture_path) == FIXTURE["sha256"], "fixture physical bytes/hash drift")
    except OSError:
        errors.append("fixture cannot be read")
    check(errors, manifest.get("inventory") == {"canonical_sha256": STABLE_SHA256, "count": len(STABLE_NAMES), "names": list(STABLE_NAMES)}, "manifest inventory drift")
    check(errors, manifest.get("claims") == {"global_row_closed": False, "independent_implementation": False, "payload_parity": True, "payload_scope": "fixed_pb03_stable_array_subset", "product_capability": False, "release_approval": False, "whole_payload_parity": False}, "manifest claims drift")
    check(errors, manifest.get("non_claims") == [*FIXED_NON_CLAIMS, "No bit-reproducible build claim is made; raw binary identity may vary between fresh runs."], "manifest non-claims drift")
    check(errors, manifest.get("replay_policy") == {"fresh_runs_required": 2, "source_mode": "git_archive_at_immutable_commit", "external_fresh_roots": True, "no_promotion": True}, "manifest replay policy drift")
    evidence = manifest.get("evidence")
    check(errors, isinstance(evidence, dict) and set(evidence) == {"aggregate", "reports"}, "manifest evidence schema drift")
    if isinstance(evidence, dict):
        report_bindings = evidence.get("reports")
        check(errors, report_bindings == list(REPORTS), "manifest report bindings drift")
        check(errors, evidence.get("aggregate") == AGGREGATE, "manifest aggregate binding drift")
    audit = manifest.get("audit")
    check(errors, isinstance(audit, dict) and set(audit) == {"path", "sha256"}, "manifest audit binding drift")
    audit_value: dict[str, Any] | None = None
    if isinstance(audit, dict):
        check(errors, audit.get("path") == AUDIT_PATH and isinstance(audit.get("sha256"), str) and HEX64.fullmatch(audit["sha256"]) is not None, "manifest audit reference malformed")
        if repo_relative(audit.get("path")):
            audit_path = ROOT / audit["path"]
            try:
                audit_value = json.loads(audit_path.read_text(encoding="utf-8"))
                check(errors, digest(audit_path) == audit.get("sha256"), "audit digest drift")
            except (OSError, ValueError) as error:
                errors.append(f"audit cannot be loaded: {error}")
    harness = manifest.get("harness")
    check(errors, isinstance(harness, dict) and set(harness) == {"aggregate_tests", "aggregator", "helper", "mutation_tests", "runner", "verifier"}, "manifest harness schema drift")
    if isinstance(harness, dict):
        expected_harness = {
            "runner": ("tools/run_pb_03_direct_replay.py", "c54f238c9bc4a21c62107b939625c75f967558d33098366c017ab928b5709d51"),
            "helper": ("tools/pb_03_replay_common.py", "bd10f6bbc63bde8fe3b7f1fb2083ac568ca41d2c42d21faedf127f8b6540d5c9"),
            "aggregator": ("tools/aggregate_pb_03_05_direct_replay.py", "a11bb2ad01ed9610e4da25cba6fd43261473d12afb68df8d4ade7545038c9ac7"),
        }
        for key, (path, expected_sha) in expected_harness.items():
            item = harness.get(key)
            check(errors, isinstance(item, dict) and item.get("path") == path and item.get("sha256") == expected_sha and repo_relative(path), f"manifest {key} harness drift")
            if isinstance(item, dict) and repo_relative(item.get("path")):
                physical = ROOT / item["path"]
                check(errors, physical.is_file() and digest(physical) == expected_sha, f"manifest {key} physical hash drift")
        for key in ("verifier", "mutation_tests", "aggregate_tests"):
            item = harness.get(key)
            expected_path = VERIFIER_PATH if key == "verifier" else MUTATION_TEST_PATH if key == "mutation_tests" else AGGREGATE_TEST_PATH
            check(errors, isinstance(item, dict) and item.get("path") == expected_path and isinstance(item.get("sha256"), str) and HEX64.fullmatch(item.get("sha256", "")) is not None, f"manifest {key} harness malformed")
            if isinstance(item, dict) and repo_relative(item.get("path")):
                physical = ROOT / item["path"]
                check(errors, physical.is_file() and digest(physical) == item.get("sha256"), f"manifest {key} physical hash drift")
    report_values: list[dict[str, Any]] = []
    for expected in REPORTS:
        report, actual = load_json(expected["path"], errors, expected["path"])
        check(errors, actual == expected["sha256"], f"{expected['path']} immutable hash drift")
        if report is not None:
            verify_report(report, expected, errors, expected["path"])
            check(errors, path_free(report), f"{expected['path']} contains an absolute host path")
            report_values.append(report)
    aggregate, aggregate_actual = load_json(AGGREGATE["path"], errors, AGGREGATE["path"])
    check(errors, aggregate_actual == AGGREGATE["sha256"], "aggregate immutable hash drift")
    if aggregate is not None:
        check(errors, set(aggregate) == {"binary_gate", "blockers", "builds", "candidate", "claims", "distinct_gate", "fixture", "non_claims", "payload", "reports", "row", "schema", "status", "toolchain", "upstream", "workflow_semantics"}, "aggregate schema drift")
        check(errors, aggregate.get("schema") == "sipi.pb-direct-replay-aggregate.v1" and aggregate.get("row") == "PB-03" and aggregate.get("status") == "passed" and aggregate.get("blockers") == [], "aggregate status drift")
        check(errors, aggregate.get("candidate") == CANDIDATE and aggregate.get("upstream") == UPSTREAM and aggregate.get("fixture") == {**FIXTURE, "archive_present": True} and aggregate.get("toolchain") == EXPECTED_TOOLCHAIN, "aggregate identity drift")
        check(errors, aggregate.get("payload") == {"candidate_logical_sha256": STABLE_SHA256, "equal": True, "oracle_logical_sha256": STABLE_SHA256}, "aggregate payload drift")
        check(errors, aggregate.get("claims") == {"global_row_closed": False, "independent_implementation": False, "payload_parity": True, "payload_scope": "fixed_pb03_stable_array_subset", "release_approval": False, "whole_payload_parity": False}, "aggregate claims drift")
        check(errors, aggregate.get("non_claims") == [
            "A frozen fixture does not cover all branches.",
            "PB-03 payload parity is only the fixed stable array subset, not whole-payload parity.",
            "The candidate and oracle do not prove independent implementations.",
            "Uncovered branches, global parity, product capability, and release approval remain open.",
            "No bit-reproducible build claim is made; raw binary identity may vary between fresh runs.",
        ], "aggregate non-claims drift")
        check(errors, aggregate.get("binary_gate") == {"candidate_binary_matches_raw": True, "canonical_binary_sha256_equal": False, "no_bit_reproducible_build_claim": True, "raw_binary_sha256_distinct": True}, "aggregate binary gate drift")
        if len(report_values) == 2:
            expected_builds = []
            builds_valid = True
            for report in report_values:
                build = report.get("build")
                custody = build.get("binary_custody") if isinstance(build, dict) else None
                if not isinstance(build, dict) or not isinstance(custody, dict):
                    builds_valid = False
                    continue
                expected_builds.append({
                    "exit_code": 0,
                    "binary_sha256": build["binary_sha256"],
                    "binary_custody": {key: custody[key] for key in ("bytes", "canonical_sha256", "machine", "profile", "raw_sha256", "repro_entry")},
                })
            check(errors, builds_valid and aggregate.get("builds") == expected_builds, "aggregate build custody drift")
        check(errors, aggregate.get("workflow_semantics") == {
            "first": {"candidate": None, "expected": None, "oracle": None},
            "second": {"candidate": None, "expected": None, "oracle": None},
            "compare_first": {"candidate": None, "oracle": None, "payload_gate": None},
            "compare_second": {"candidate": None, "oracle": None, "payload_gate": None},
            "payload_is_not_status_only": True,
        }, "aggregate workflow semantics drift")
        check(errors, aggregate.get("distinct_gate") == {"exact_toolchain_identity": True, "unique_fresh_run_nonces": True, "unique_report_paths": True, "unique_report_sha256": True, "unique_run_ids": True}, "aggregate distinct gate drift")
        check(errors, aggregate.get("reports") == [{"fresh_run_nonce": item["fresh_run_nonce"], "path": item["path"], "payload": {"candidate_logical_sha256": STABLE_SHA256, "equal": True, "oracle_logical_sha256": STABLE_SHA256}, "run_id": item["run_id"], "sha256": item["sha256"]} for item in REPORTS], "aggregate report graph drift")
        check(errors, path_free(aggregate), "aggregate contains an absolute host path")
    if len(report_values) == 2:
        check(errors, report_values[0]["fresh_run_nonce"] != report_values[1]["fresh_run_nonce"] and report_values[0]["run_id"] != report_values[1]["run_id"], "fresh run identity is not distinct")
        check(errors, report_values[0]["toolchain"] == report_values[1]["toolchain"] and report_values[0]["candidate"] == report_values[1]["candidate"] and report_values[0]["upstream"] == report_values[1]["upstream"], "cross-run identity drift")
        verify_member_map(report_values[0], errors, "run-01")
        verify_member_map(report_values[1], errors, "run-02")
        for side in ("candidate_artifact", "oracle_artifact"):
            first_replay = report_values[0].get("replay")
            second_replay = report_values[1].get("replay")
            first = first_replay.get(side) if isinstance(first_replay, dict) else None
            second = second_replay.get(side) if isinstance(second_replay, dict) else None
            first_arrays = first.get("arrays", {}) if isinstance(first, dict) else {}
            second_arrays = second.get("arrays", {}) if isinstance(second, dict) else {}
            check(
                errors,
                isinstance(first, dict)
                and isinstance(second, dict)
                and isinstance(first_arrays, dict)
                and isinstance(second_arrays, dict)
                and first_arrays.get("logical_members") == second_arrays.get("logical_members"),
                f"cross-run {side} stable array map drift",
            )
    if audit_value is not None:
        check(errors, set(audit_value) == {"aggregate", "claims", "exact_file_bindings", "inventory", "manifest_path", "no_bit_reproducible_build_claim", "non_claims", "row", "schema", "source_map"}, "audit schema drift")
        harness_for_audit = harness if isinstance(harness, dict) else {}
        expected_bindings = {"aggregate": AGGREGATE, "report_01": REPORTS[0], "report_02": REPORTS[1], "runner": harness_for_audit.get("runner"), "helper": harness_for_audit.get("helper"), "aggregator": harness_for_audit.get("aggregator"), "aggregate_tests": harness_for_audit.get("aggregate_tests"), "mutation_tests": harness_for_audit.get("mutation_tests"), "verifier": harness_for_audit.get("verifier")}
        check(errors, audit_value.get("schema") == "sipi.pb-03-ed7b12d2-audit.v1" and audit_value.get("row") == "PB-03" and audit_value.get("manifest_path") == MANIFEST_PATH, "audit identity drift")
        check(errors, audit_value.get("source_map") == "not_applicable_for_scoped_observation", "audit source map drift")
        check(errors, audit_value.get("inventory") == {"canonical_sha256": STABLE_SHA256, "count": len(STABLE_NAMES), "names": list(STABLE_NAMES)}, "audit inventory drift")
        check(errors, audit_value.get("aggregate") == AGGREGATE, "audit aggregate binding drift")
        check(errors, audit_value.get("exact_file_bindings") == expected_bindings, "audit file bindings drift")
        check(errors, audit_value.get("no_bit_reproducible_build_claim") is True and audit_value.get("claims") == manifest.get("claims") and audit_value.get("non_claims") == manifest.get("non_claims"), "audit claim drift")
    check(errors, path_free(manifest) and path_free(audit_value), "evidence contains an absolute host path")
    return {"valid": not errors, "errors": errors}


def main() -> int:
    manifest_path = ROOT / MANIFEST_PATH
    try:
        import yaml

        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        result = verify(manifest)
    except (OSError, ValueError, TypeError) as error:
        result = {"valid": False, "errors": [f"blocked: {error}"]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
