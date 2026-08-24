"""Fail-closed verifier for the PB-02 43c12 additive evidence successor."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/pb-02-direct-43c12-current.v2.yaml"
AUDIT_PATH = "docs/baselines/audits/2026-08-24-pb-02-direct-43c12.v2.json"
REPORT_PATHS = (
    "docs/baselines/pb-02-direct-43c12-current-run-01.json",
    "docs/baselines/pb-02-direct-43c12-current-run-02.json",
)
AGGREGATE_PATH = "docs/baselines/pb-02-direct-43c12-current-aggregate.json"
EXPECTED_CANDIDATE = {
    "commit": "43c12e0825a8c28125d195ec69750e696c6f470f",
    "tree": "2e146d6f10759126f42d03548dc724166be783ce",
    "archive_sha256": "c08a6a5c7bcd73b515d58794e196491622c6d857175417aa8fde322ef7c728a3",
}
EXPECTED_UPSTREAM = {
    "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
    "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
    "archive_sha256": "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25",
}
EXPECTED_FIXTURE = {
    "path": "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json",
    "sha256": "5bcd0b905f8a7f0ec5e2b7c3761a998e9553ac24a71b54f8b0d4e8e84261ea13",
    "bytes": 1245,
    "archive_present": True,
}
EXPECTED_MEMBER_NAMES = (
    "channel_impulse_v_per_v.npy",
    "channel_output_v.npy",
    "ctle_output_v.npy",
    "rx_ffe_impulse_v_per_v.npy",
    "rx_filter_impulse_v_per_v.npy",
    "rx_input_v.npy",
    "rx_output_v.npy",
    "symbols_v.npy",
    "time_s.npy",
    "tx_channel_impulse_v_per_v.npy",
    "tx_waveform_v.npy",
)
EXPECTED_LOGICAL_SHA = "5090a1478ea6e985342d8500c6220cdde5c7fa2c416abbdeb595dcdc380c275a"
EXPECTED_BUILD_BINARY_SHA = (
    "857e7b32460665949d5bdd8bbbe283ba86022ab248ebf932142444e07a2d4678",
    "cdeb7f5412d8ad89dce711788f1a63105338485889c960dafb19751550523229",
)
EXPECTED_REPORT_REFS = (
    {
        "path": "docs/baselines/pb-02-direct-43c12-current-run-01.json",
        "sha256": "9906e4801dc462242ad064db3899cc98ea74f9eb81d24ad210859c3d8647034c",
        "run_id": "pb02-43c12-run-01",
        "fresh_run_nonce": "92c6ea25ab22d3f2c4d4102892e4c5aebe8f1bf2ad9d2559338282c15ee1136e",
    },
    {
        "path": "docs/baselines/pb-02-direct-43c12-current-run-02.json",
        "sha256": "6956f44c3a25c211e32f3bd32e882d9cb5e01aec5713c215d130b8db8268fd4e",
        "run_id": "pb02-43c12-run-02",
        "fresh_run_nonce": "8f6b306fa858744e7cb4cda54378034cf29384829d2fb9e7e43aa663be86a1e2",
    },
)
EXPECTED_AGGREGATE_REF = {
    "path": "docs/baselines/pb-02-direct-43c12-current-aggregate.json",
    "sha256": "30253d5ec770ea69187d9211dcc5bb6700447c6eb052d7ac8b5155dc3b763c15",
}
EXPECTED_INVENTORY_SHA = {
    "candidate": "5ca754497b55461ef62fcae1148ac93f2f9f0b772d7d7983089b507254d19d2e",
    "upstream": "26ccbee692b9c4984c6cee0cff6c3987fc013e914905a66019937f940a5abfb9",
}
EXPECTED_HARNESS = {
    "runner": ("tools/run_pb_02_direct_replay.py", "c7839a7d67425fda0df675c35925a87f7e3527996fa3b659e2ee7c036408d863"),
    "aggregator": ("tools/aggregate_pb_02_direct_replay.py", "04a2d35fd7f1df1fc3728c0918fc752980b0e7c718eedf5a0285ff0bae24043a"),
    # The verifier cannot embed its own digest without a circular hash.  Its
    # exact path is fixed here; the manifest/audit bind its physical digest.
    "verifier": ("tools/verify_pb_02_direct_43c12_current.py", None),
    "mutation_tests": ("tools/test_verify_pb_02_direct_43c12_current.py", None),
}
EXPECTED_REPORT_NON_CLAIMS = [
    "This report does not prove parity for uncovered SimulationInputV1 branches.",
    "SIPI strict JSON, artifact, NPZ compression, and symlink policies are wrapper behavior, not upstream sim-native semantics.",
    "The report is not a license decision, release approval, or product capability admission.",
]
EXPECTED_AGGREGATE_NON_CLAIMS = [
    "This aggregate proves only the one explicit PB-02 fixture and does not close uncovered SimulationInputV1 branches.",
    "SIPI wrapper admission and artifact policies remain outside upstream numerical parity.",
    "This aggregate is not a license decision, release approval, or product capability admission.",
]
EXPECTED_NON_CLAIMS = [
    "explicit fixture only",
    "not independent implementation",
    "not pure-Python legacy sim parity",
    "uncovered SimulationInputV1 branches remain open",
    "external AMI/IBIS/DLL/TS4 assets remain quarantined",
    "environment-local toolchain custody, not cross-machine reproducibility",
    "no bit-reproducible build claim",
    "not a license decision, release approval, or product capability admission",
]
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_json(path: Path) -> tuple[dict[str, Any] | None, str | None, str | None]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, None, type(error).__name__
    if not isinstance(value, dict):
        return None, _sha256(raw), "not_object"
    return value, _sha256(raw), None


def _relative_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value
        and not value.startswith(("/", "\\"))
        and ":" not in value
        and ".." not in value.split("/")
        and "\\" not in value
    )


def _exact_keys(value: Any, expected: set[str], label: str, blockers: list[str]) -> bool:
    if not isinstance(value, dict) or set(value) != expected:
        blockers.append(f"{label} schema is not exact")
        return False
    return True


def _digest(value: Any, label: str, blockers: list[str]) -> bool:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        blockers.append(f"{label} is not lowercase sha256")
        return False
    return True


def _finite_summary(summary: Any, name: str, blockers: list[str]) -> bool:
    if not isinstance(summary, dict):
        blockers.append(f"{name} logical summary is missing")
        return False
    if set(summary) != {"count", "dtype", "f64_sha256", "fortran_order", "shape"}:
        blockers.append(f"{name} logical summary schema is not exact")
        return False
    shape = summary.get("shape")
    count = summary.get("count")
    if summary.get("dtype") != "<f8" or summary.get("fortran_order") is not False:
        blockers.append(f"{name} dtype/order contract failed")
    if not isinstance(shape, list) or not shape or any(type(item) is not int or item <= 0 for item in shape):
        blockers.append(f"{name} shape is invalid")
    elif type(count) is not int or count < 0 or math.prod(shape) != count:
        blockers.append(f"{name} count/shape contract failed")
    _digest(summary.get("f64_sha256"), f"{name} f64 digest", blockers)
    return True


def _check_arrays(value: Any, side: str, blockers: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        blockers.append(f"{side} arrays missing")
        return None
    if set(value) != {"bytes", "logical_members", "logical_sha256", "member_bytes", "member_sha256", "sha256"}:
        blockers.append(f"{side} arrays schema is not exact")
        return None
    if type(value.get("bytes")) is not int or value["bytes"] <= 0:
        blockers.append(f"{side} arrays bytes contract failed")
    for key in ("sha256", "logical_sha256"):
        _digest(value.get(key), f"{side} arrays {key}", blockers)
    members = value.get("logical_members")
    if not isinstance(members, dict) or tuple(sorted(members)) != EXPECTED_MEMBER_NAMES:
        blockers.append(f"{side} logical member names are not the exact 11 names")
        return None
    for name in EXPECTED_MEMBER_NAMES:
        _finite_summary(members.get(name), f"{side}.{name}", blockers)
    member_bytes = value.get("member_bytes")
    member_sha = value.get("member_sha256")
    if not isinstance(member_bytes, dict) or tuple(sorted(member_bytes)) != EXPECTED_MEMBER_NAMES:
        blockers.append(f"{side} member_bytes map is not exact")
    elif any(type(item) is not int or item <= 0 for item in member_bytes.values()):
        blockers.append(f"{side} member_bytes values are invalid")
    if not isinstance(member_sha, dict) or tuple(sorted(member_sha)) != EXPECTED_MEMBER_NAMES:
        blockers.append(f"{side} member_sha256 map is not exact")
    elif any(not isinstance(item, str) or HEX64.fullmatch(item) is None for item in member_sha.values()):
        blockers.append(f"{side} member_sha256 values are invalid")
    if _sha256(_canonical(members)) != value.get("logical_sha256"):
        blockers.append(f"{side} logical sha is not the canonical member-map sha")
    if value.get("logical_sha256") != EXPECTED_LOGICAL_SHA:
        blockers.append(f"{side} logical sha drift")
    return members


def _check_process(value: Any, side: str, blockers: list[str]) -> dict[str, Any] | None:
    if not _exact_keys(value, {"artifacts", "exit_code", "stderr_sha256", "stdout_sha256"}, side, blockers):
        return None
    if value.get("exit_code") != 0:
        blockers.append(f"{side} exit is not zero")
    _digest(value.get("stderr_sha256"), f"{side} stderr digest", blockers)
    _digest(value.get("stdout_sha256"), f"{side} stdout digest", blockers)
    artifacts = value.get("artifacts")
    expected_artifacts = {"arrays", "arrays_present", "meta_json_valid", "meta_normalized_sha256", "meta_present", "meta_schema", "meta_sha256"}
    if not _exact_keys(artifacts, expected_artifacts, f"{side}.artifacts", blockers) or artifacts.get("arrays_present") is not True:
        blockers.append(f"{side} arrays artifact is missing")
        return None
    if artifacts.get("meta_present") is not True or artifacts.get("meta_json_valid") is not True or artifacts.get("meta_schema") != "pybert.native-cli-result.v1":
        blockers.append(f"{side} metadata contract failed")
    for key in ("meta_sha256", "meta_normalized_sha256"):
        _digest(artifacts.get(key), f"{side} {key}", blockers)
    arrays = artifacts.get("arrays")
    return _check_arrays(arrays, side, blockers)


def _check_toolchain(value: Any, label: str, blockers: list[str]) -> bool:
    if not _exact_keys(value, {"cargo", "rustc", "uv", "timeout_seconds"}, label, blockers):
        return False
    if type(value.get("timeout_seconds")) is not int or value["timeout_seconds"] <= 0:
        blockers.append(f"{label} timeout is invalid")
    for role in ("cargo", "rustc", "uv"):
        identity = value.get(role)
        if not _exact_keys(identity, {"role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"}, f"{label}.{role}", blockers):
            continue
        if identity.get("role") != role or identity.get("path_redacted") is not True or identity.get("version_exit_code") != 0:
            blockers.append(f"{label}.{role} identity contract failed")
        executable = identity.get("executable")
        if not isinstance(executable, str) or not executable or any(token in executable for token in ("/", "\\", ":")):
            blockers.append(f"{label}.{role} executable is not a basename")
        _digest(identity.get("file_sha256"), f"{label}.{role} file_sha256", blockers)
        _digest(identity.get("version_output_sha256"), f"{label}.{role} version_output_sha256", blockers)
    return True


def _check_report(document: Any, label: str, blockers: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(document, dict):
        blockers.append(f"{label} report is not an object")
        return None, None
    expected_top = {"candidate", "custody", "fixture", "fresh_run_nonce", "non_claims", "replay", "run_id", "schema", "source_mode", "status", "toolchain", "upstream"}
    if not _exact_keys(document, expected_top, label, blockers):
        return None, None
    if document.get("schema") != "sipi.pb-02-direct-replay.v1" or document.get("status") != "passed" or document.get("source_mode") != "git_archive_at_immutable_commit":
        blockers.append(f"{label} status/source contract failed")
    if not isinstance(document.get("run_id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", document["run_id"]):
        blockers.append(f"{label} run id malformed")
    _digest(document.get("fresh_run_nonce"), f"{label} nonce", blockers)
    if document.get("non_claims") != EXPECTED_REPORT_NON_CLAIMS:
        blockers.append(f"{label} non_claims are not exact")
    if not _exact_keys(document.get("fixture"), set(EXPECTED_FIXTURE), f"{label}.fixture", blockers) or document.get("fixture") != EXPECTED_FIXTURE:
        blockers.append(f"{label} fixture drift")
    for side, expected in (("candidate", EXPECTED_CANDIDATE), ("upstream", EXPECTED_UPSTREAM)):
        value = document.get(side)
        if not isinstance(value, dict):
            blockers.append(f"{label}.{side} missing")
        elif any(value.get(key) != expected_value for key, expected_value in expected.items()):
            blockers.append(f"{label}.{side} immutable identity drift")
        if side == "candidate" and isinstance(value, dict):
            if set(value) != {"archive_sha256", "cargo_lock_sha256", "commit", "inventory", "rust_toolchain_sha256", "tree"}:
                blockers.append(f"{label}.candidate schema is not exact")
        if side == "upstream" and isinstance(value, dict):
            if set(value) != {"archive_sha256", "commit", "inventory", "license_sha256", "native_core_cargo_lock_sha256", "tree", "uv_lock_sha256"}:
                blockers.append(f"{label}.upstream schema is not exact")
        if isinstance(value, dict) and isinstance(value.get("inventory"), dict):
            inventory = value["inventory"]
            if set(inventory) != {"entries", "sha256"}:
                blockers.append(f"{label}.{side}.inventory schema is not exact")
            _digest(inventory.get("sha256"), f"{label}.{side}.inventory sha", blockers)
            expected_inventory_sha = EXPECTED_INVENTORY_SHA.get(side)
            if expected_inventory_sha is not None and inventory.get("sha256") != expected_inventory_sha:
                blockers.append(f"{label}.{side}.inventory immutable sha drift")
            entries = inventory.get("entries")
            if not isinstance(entries, list):
                blockers.append(f"{label}.{side}.inventory entries are missing")
            else:
                for entry in entries:
                    if not _exact_keys(entry, {"bytes", "path", "sha256"}, f"{label}.{side}.inventory entry", blockers):
                        continue
                    if not _relative_path(entry.get("path")) or type(entry.get("bytes")) is not int or entry["bytes"] < 0:
                        blockers.append(f"{label}.{side}.inventory entry is unsafe")
                    _digest(entry.get("sha256"), f"{label}.{side}.inventory entry sha", blockers)
                if _sha256(_canonical(entries)) != inventory.get("sha256"):
                    blockers.append(f"{label}.{side}.inventory canonical sha drift")
    custody = document.get("custody")
    expected_custody = {"materialized_archives_created_new", "run_root_created_new", "run_root_path_redacted", "work_root_empty_before_run", "work_root_outside_candidate_repo", "work_root_outside_upstream_repo", "work_root_path_redacted"}
    if not _exact_keys(custody, expected_custody, f"{label}.custody", blockers) or not isinstance(custody, dict) or any(value is not True for value in custody.values()):
        blockers.append(f"{label} external fresh-root custody failed")
    replay = document.get("replay")
    if not _exact_keys(replay, {"build", "candidate", "oracle", "parity"}, f"{label}.replay", blockers):
        return None, None
    build = replay.get("build")
    if not _exact_keys(build, {"binary_bytes", "binary_sha256", "exit_code", "stderr_sha256", "stdout_sha256"}, f"{label}.build", blockers):
        return None, None
    if build.get("exit_code") != 0 or not isinstance(build.get("binary_bytes"), int) or build["binary_bytes"] <= 0:
        blockers.append(f"{label} candidate build failed")
    _digest(build.get("binary_sha256"), f"{label} binary digest", blockers)
    _digest(build.get("stderr_sha256"), f"{label} build stderr digest", blockers)
    _digest(build.get("stdout_sha256"), f"{label} build stdout digest", blockers)
    candidate_members = _check_process(replay.get("candidate"), f"{label}.candidate", blockers)
    oracle_members = _check_process(replay.get("oracle"), f"{label}.oracle", blockers)
    if candidate_members != oracle_members:
        blockers.append(f"{label} candidate/oracle logical member maps differ")
    parity = replay.get("parity")
    if not _exact_keys(parity, {"array_member_names", "candidate_array_members_equal_oracle", "candidate_exit_zero", "oracle_exit_zero"}, f"{label}.parity", blockers):
        return None, None
    if parity.get("candidate_array_members_equal_oracle") is not True or parity.get("candidate_exit_zero") is not True or parity.get("oracle_exit_zero") is not True or parity.get("array_member_names") != list(EXPECTED_MEMBER_NAMES):
        blockers.append(f"{label} parity contract failed")
    _check_toolchain(document.get("toolchain"), f"{label}.toolchain", blockers)
    return replay, candidate_members


def _manifest_binding(document: dict[str, Any]) -> str | None:
    copy = json.loads(json.dumps(document))
    audit = copy.get("audit")
    if not isinstance(audit, dict) or "sha256" not in audit:
        return None
    audit["sha256"] = "<audit-sha256>"
    return _sha256(_canonical(copy))


def verify(manifest_path: Path = MANIFEST) -> list[str]:
    blockers: list[str] = []
    manifest, manifest_sha, error = _safe_json(manifest_path)
    if error or manifest is None:
        return [f"manifest unreadable: {error}"]
    expected_top = {"schema", "version", "row", "status", "claims", "source", "fixture", "replay_policy", "payload", "harness", "audit", "non_claims"}
    if not _exact_keys(manifest, expected_top, "manifest", blockers):
        return blockers
    if manifest.get("schema") != "sipi.pb-02-direct-replay-current.v2" or manifest.get("version") != 2 or manifest.get("row") != "PB-02" or manifest.get("status") != "scoped_numeric_parity_environment_local":
        blockers.append("manifest identity/status drift")
    expected_claims = {"external_asset_parity": False, "fixture_payload_parity": True, "global_row_closed": False, "independent_execution_roots": True, "promotion": False}
    if manifest.get("claims") != expected_claims:
        blockers.append("claims are not exact")
    if manifest.get("non_claims") != EXPECTED_NON_CLAIMS:
        blockers.append("non_claims are not exact")
    source = manifest.get("source")
    if not _exact_keys(source, {"candidate", "upstream"}, "manifest.source", blockers):
        return blockers
    if source.get("candidate") != EXPECTED_CANDIDATE or source.get("upstream") != EXPECTED_UPSTREAM:
        blockers.append("manifest source identity drift")
    if manifest.get("fixture") != EXPECTED_FIXTURE:
        blockers.append("manifest fixture drift")
    policy = manifest.get("replay_policy")
    expected_policy_keys = {"aggregate", "external_work_root_required", "fresh_runs_required", "reports", "source_mode", "working_tree_overlay", "independent_execution_roots"}
    if not _exact_keys(policy, expected_policy_keys, "replay_policy", blockers):
        return blockers
    if policy.get("source_mode") != "git_archive_at_immutable_commit" or policy.get("working_tree_overlay") is not False or policy.get("external_work_root_required") is not True or policy.get("fresh_runs_required") != 2 or policy.get("independent_execution_roots") is not True:
        blockers.append("replay policy values are not exact")
    reports = policy.get("reports")
    if not isinstance(reports, list) or len(reports) != 2:
        blockers.append("replay policy report list is not exact")
        reports = []
    aggregate_ref = policy.get("aggregate")
    if not _exact_keys(aggregate_ref, {"path", "sha256"}, "replay_policy.aggregate", blockers):
        aggregate_ref = {}
    for index, expected_path in enumerate(REPORT_PATHS):
        if index >= len(reports) or not _exact_keys(reports[index], {"fresh_run_nonce", "path", "run_id", "sha256"}, f"replay_policy.reports[{index}]", blockers):
            continue
        ref = reports[index]
        if ref != EXPECTED_REPORT_REFS[index]:
            blockers.append(f"report {index} immutable reference drift")
        if ref.get("path") != expected_path or not _relative_path(ref.get("path")):
            blockers.append(f"report {index} path drift")
        _digest(ref.get("sha256"), f"report {index} sha", blockers)
        _digest(ref.get("fresh_run_nonce"), f"report {index} nonce", blockers)
    if aggregate_ref.get("path") != AGGREGATE_PATH or not _relative_path(aggregate_ref.get("path")):
        blockers.append("aggregate path drift")
    _digest(aggregate_ref.get("sha256"), "aggregate sha", blockers)
    if aggregate_ref != EXPECTED_AGGREGATE_REF:
        blockers.append("aggregate immutable reference drift")
    payload = manifest.get("payload")
    expected_payload = {"candidate_exit_code": 0, "oracle_exit_code": 0, "logical_array_sha256": EXPECTED_LOGICAL_SHA, "member_count": 11, "member_names": list(EXPECTED_MEMBER_NAMES), "parity": True}
    if payload != expected_payload:
        blockers.append("payload contract is not exact")
    harness = manifest.get("harness")
    if not isinstance(harness, dict) or set(harness) != {"aggregator", "mutation_tests", "runner", "verifier"}:
        blockers.append("harness schema is not exact")
    else:
        for key in harness:
            item = harness[key]
            if not _exact_keys(item, {"path", "sha256"}, f"harness.{key}", blockers) or not _relative_path(item.get("path")):
                continue
            expected_path, expected_sha = EXPECTED_HARNESS[key]
            if item.get("path") != expected_path or (expected_sha is not None and item.get("sha256") != expected_sha):
                blockers.append(f"harness.{key} exact binding drift")
            _digest(item.get("sha256"), f"harness.{key} sha", blockers)
            actual, actual_sha, read_error = _safe_json(ROOT / item["path"]) if item["path"].endswith(".json") else (None, _sha256((ROOT / item["path"]).read_bytes()) if (ROOT / item["path"]).is_file() else None, None)
            if actual_sha != item.get("sha256"):
                blockers.append(f"harness.{key} physical sha drift")
    audit = manifest.get("audit")
    if not _exact_keys(audit, {"path", "sha256"}, "manifest.audit", blockers) or audit.get("path") != AUDIT_PATH or not _relative_path(audit.get("path")):
        blockers.append("manifest audit binding drift")
    audit_doc, audit_sha, audit_error = _safe_json(ROOT / AUDIT_PATH)
    if audit_error or audit_doc is None or not isinstance(audit, dict) or audit_sha != audit.get("sha256"):
        blockers.append("audit missing or sha drift")
    elif _manifest_binding(manifest) is None or _manifest_binding(manifest) != audit_doc.get("manifest_binding_sha256"):
        blockers.append("audit manifest binding drift")
    if audit_doc is not None:
        expected_audit_keys = {"schema", "row", "status", "source_map", "exact_file_bindings", "archive_harness", "claims", "non_claims", "manifest_binding_sha256"}
        if not _exact_keys(audit_doc, expected_audit_keys, "audit", blockers):
            pass
        elif audit_doc.get("source_map") != "not_applicable_for_scoped_observation" or audit_doc.get("schema") != "sipi.pb-02-direct-audit.v2" or audit_doc.get("row") != "PB-02" or audit_doc.get("status") != manifest.get("status"):
            blockers.append("audit status/source_map drift")
        else:
            binding = audit_doc["exact_file_bindings"]
            expected_binding_names = {"report_01", "report_02", "aggregate", "manifest", "runner", "aggregator", "verifier", "mutation_tests"}
            if not _exact_keys(binding, expected_binding_names, "audit.exact_file_bindings", blockers):
                pass
            else:
                for key in ("runner", "aggregator", "verifier", "mutation_tests"):
                    item = binding[key]
                    if not _exact_keys(item, {"path", "sha256"}, f"audit.{key}", blockers) or item != harness.get(key):
                        blockers.append(f"audit {key} binding drift")
                for index, key in enumerate(("report_01", "report_02")):
                    item = binding[key]
                    if not _exact_keys(item, {"path", "sha256", "run_id", "fresh_run_nonce"}, f"audit.{key}", blockers):
                        continue
                    if index >= len(reports) or not isinstance(reports[index], dict) or item.get("path") != reports[index].get("path") or item.get("sha256") != reports[index].get("sha256") or item.get("run_id") != reports[index].get("run_id") or item.get("fresh_run_nonce") != reports[index].get("fresh_run_nonce"):
                        blockers.append(f"audit report {index} binding drift")
                aggregate_item = binding["aggregate"]
                if not _exact_keys(aggregate_item, {"path", "sha256"}, "audit.aggregate", blockers) or aggregate_item != aggregate_ref:
                    blockers.append("audit aggregate binding drift")
                manifest_item = binding["manifest"]
                if not _exact_keys(manifest_item, {"path", "binding_sha256"}, "audit.manifest", blockers) or manifest_item.get("path") != "docs/baselines/pb-02-direct-43c12-current.v2.yaml" or manifest_item.get("binding_sha256") != audit_doc.get("manifest_binding_sha256"):
                    blockers.append("audit manifest binding drift")
            archive = audit_doc["archive_harness"]
            expected_archive_keys = {"source_mode", "working_tree_overlay", "external_work_root_required", "candidate_commit", "candidate_tree", "candidate_archive_sha256", "upstream_commit", "upstream_tree", "upstream_archive_sha256", "fixture_path", "fixture_sha256", "fixture_bytes"}
            expected_archive = {
                "source_mode": "git_archive_at_immutable_commit",
                "working_tree_overlay": False,
                "external_work_root_required": True,
                "candidate_commit": EXPECTED_CANDIDATE["commit"],
                "candidate_tree": EXPECTED_CANDIDATE["tree"],
                "candidate_archive_sha256": EXPECTED_CANDIDATE["archive_sha256"],
                "upstream_commit": EXPECTED_UPSTREAM["commit"],
                "upstream_tree": EXPECTED_UPSTREAM["tree"],
                "upstream_archive_sha256": EXPECTED_UPSTREAM["archive_sha256"],
                "fixture_path": EXPECTED_FIXTURE["path"],
                "fixture_sha256": EXPECTED_FIXTURE["sha256"],
                "fixture_bytes": EXPECTED_FIXTURE["bytes"],
            }
            if not _exact_keys(archive, expected_archive_keys, "audit.archive_harness", blockers) or archive != expected_archive:
                blockers.append("audit archive harness drift")
            if audit_doc.get("claims") != manifest.get("claims"):
                blockers.append("audit claims drift")
            if audit_doc.get("non_claims") != manifest.get("non_claims"):
                blockers.append("audit non_claims drift")
    documents: list[dict[str, Any]] = []
    for index, expected_path in enumerate(REPORT_PATHS):
        document, report_sha, report_error = _safe_json(ROOT / expected_path)
        if report_error or document is None:
            blockers.append(f"report {index} unreadable: {report_error}")
            continue
        documents.append(document)
        if index < len(reports):
            if isinstance(reports[index], dict) and report_sha != reports[index].get("sha256"):
                blockers.append(f"report {index} physical sha drift")
            elif not isinstance(reports[index], dict):
                blockers.append(f"report {index} reference is malformed")
        if index < len(EXPECTED_REPORT_REFS) and (report_sha != EXPECTED_REPORT_REFS[index]["sha256"] or document.get("run_id") != EXPECTED_REPORT_REFS[index]["run_id"] or document.get("fresh_run_nonce") != EXPECTED_REPORT_REFS[index]["fresh_run_nonce"]):
            blockers.append(f"report {index} immutable physical anchor drift")
        _check_report(document, f"report[{index}]", blockers)
        if index < len(reports) and isinstance(reports[index], dict):
            reference = reports[index]
            if document.get("run_id") != reference.get("run_id") or document.get("fresh_run_nonce") != reference.get("fresh_run_nonce"):
                blockers.append(f"report {index} run reference drift")
            if report_sha != reference.get("sha256"):
                blockers.append(f"report {index} sha reference drift")
    aggregate, aggregate_sha, aggregate_error = _safe_json(ROOT / AGGREGATE_PATH)
    if aggregate_error or aggregate is None:
        blockers.append(f"aggregate unreadable: {aggregate_error}")
    elif aggregate_sha != aggregate_ref.get("sha256"):
        blockers.append("aggregate physical sha drift")
    if aggregate_sha != EXPECTED_AGGREGATE_REF["sha256"]:
        blockers.append("aggregate immutable physical anchor drift")
    if len(documents) == 2 and aggregate is not None:
        if documents[0].get("run_id") == documents[1].get("run_id") or documents[0].get("fresh_run_nonce") == documents[1].get("fresh_run_nonce"):
            blockers.append("report run IDs and nonces must be distinct")
        if reports and all(isinstance(item, dict) for item in reports) and reports[0].get("sha256") == reports[1].get("sha256"):
            blockers.append("report full SHA references must be distinct")
        if documents[0].get("candidate") != documents[1].get("candidate") or documents[0].get("upstream") != documents[1].get("upstream") or documents[0].get("fixture") != documents[1].get("fixture"):
            blockers.append("report immutable source/fixture objects must be equal")
        for index, document in enumerate(documents):
            build = document.get("replay", {}).get("build", {})
            if build.get("binary_sha256") != EXPECTED_BUILD_BINARY_SHA[index]:
                blockers.append(f"report {index} raw binary identity drift")
        if documents[0].get("replay", {}).get("build", {}).get("binary_sha256") == documents[1].get("replay", {}).get("build", {}).get("binary_sha256"):
            blockers.append("raw candidate binary SHA must remain distinct")
        if set(aggregate) != {"blockers", "candidate", "fixture", "logical_array_member_sha256", "non_claims", "reports", "schema", "status", "toolchain", "upstream"}:
            blockers.append("aggregate schema is not exact")
        if aggregate.get("schema") != "sipi.pb-02-direct-replay-aggregate.v1" or aggregate.get("status") != "passed" or aggregate.get("blockers") != []:
            blockers.append("aggregate status/blockers failed")
        if aggregate.get("candidate") != documents[0].get("candidate") or aggregate.get("upstream") != documents[0].get("upstream") or aggregate.get("fixture") != documents[0].get("fixture"):
            blockers.append("aggregate immutable identity drift")
        if aggregate.get("toolchain") != documents[0].get("toolchain") or aggregate.get("toolchain") != documents[1].get("toolchain"):
            blockers.append("aggregate toolchain identity drift")
        if aggregate.get("non_claims") != EXPECTED_AGGREGATE_NON_CLAIMS:
            blockers.append("aggregate non_claims drift")
        if not all(isinstance(item, dict) for item in reports) or aggregate.get("reports") != [
            {"path": REPORT_PATHS[0], "sha256": reports[0]["sha256"], "run_id": reports[0]["run_id"], "fresh_run_nonce": reports[0]["fresh_run_nonce"], "logical_array_sha256": EXPECTED_LOGICAL_SHA},
            {"path": REPORT_PATHS[1], "sha256": reports[1]["sha256"], "run_id": reports[1]["run_id"], "fresh_run_nonce": reports[1]["fresh_run_nonce"], "logical_array_sha256": EXPECTED_LOGICAL_SHA},
        ]:
            blockers.append("aggregate report graph drift")
        if aggregate.get("logical_array_member_sha256") != documents[0].get("replay", {}).get("candidate", {}).get("artifacts", {}).get("arrays", {}).get("logical_members"):
            blockers.append("aggregate logical map drift")
    return blockers


def main() -> int:
    blockers = verify()
    result = {"status": "passed" if not blockers else "blocked", "blockers": blockers}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
