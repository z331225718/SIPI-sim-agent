"""Strict additive verifier for the v13 upstream integration ledger."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/baselines/upstream-integration-ledger.v13.yaml"
SCHEMA = "sipi.upstream-integration-ledger.v13"
STATUS = "current_clean_candidate_open_no_release"
COMMIT = "189ffaa85f8f21ae7cdc7b2ca8f126122d9b335f"
TREE = "f4a76932fef0a8f1f790ce682477d7639c7822de"
ARCHIVE = "3e96cf027f2aa9daa313474061cf783a0bff07fb8f896ae86c4380f9ea08ecbf"
ARCHIVE_BYTES = 55480320
PREDECESSOR_PATH = "docs/baselines/upstream-integration-ledger.v12.yaml"
PREDECESSOR_SHA = "58bd4f91a47c3c65e8c14939a815181764b48d494409ef90096308089bf9ce9c"
PLAN_PATH = "PLAN.md"
PLAN_MARKER = "2026-08-28 v13 upstream-first successor"
EXPECTED_PLAN_SHA = "bd326699137d1218512c9d9628a3392b547dd016a1a3dd6965b6b148e0c31070"
AUDIT_PATH = "docs/baselines/audits/2026-08-28-upstream-integration-ledger-v13.md"
EXPECTED_AUDIT_SHA = "661547ac35e73ca9be7316666dedd7c3bbe7dc1e2414765d47ffd83e9bb7584b"
MUTATION_TEST_PATH = "tools/test_verify_upstream_integration_ledger_v13.py"
EXPECTED_VERIFIER_SHA = "c0868125d23f3aed6c052167800c95ef48b110ac99be856f3cf725344ace8edc"
EXPECTED_MUTATION_SHA = "e5fa2838b0a0e8bc546e9cd9a5809d5428144f7183ce0219a2b60b6acfcfe893"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

ROWS = (
    ("AS-01", "agent_spice", "fit-sparam"),
    ("AS-02", "agent_spice", "fit-sparam-cascade"),
    ("AS-03", "agent_spice", "fit-yparam"),
    ("AS-04", "agent_spice", "tune-yparam-tran"),
    ("AS-05", "agent_spice", "run-hspice"),
    ("AS-06", "agent_spice", "run-rfm"),
    ("PB-01", "pybert", "sim"),
    ("PB-02", "pybert", "sim-native"),
    ("PB-03", "pybert", "sim-rust"),
    ("PB-04", "pybert", "sim-auto"),
    ("PB-05", "pybert", "sim-compare"),
    ("COM-01", "agent_com", "config-validate"),
    ("COM-02", "agent_com", "run"),
    ("COM-03", "agent_com", "compare"),
    ("COM-04", "agent_com", "load_config-run_com-write_artifacts"),
)

POLICY = {
    "AS-01": ("excluded_fail_closed", "unavailable", "historical_only", "excluded_no_release"),
    "AS-02": ("excluded_fail_closed", "unavailable", "historical_only", "excluded_no_release"),
    "AS-03": ("retained_external_runtime", "external_solver_required", "scoped_numeric_mismatch_open", "open_no_release"),
    "AS-04": ("direct_rust_port", "external_solver_required", "external_blocker_observed", "open_no_release"),
    "AS-05": ("direct_rust_port", "external_solver_required", "external_solver_not_verified", "open_no_release"),
    "AS-06": ("direct_rust_port", "external_solver_required", "scoped_observation", "open_no_release"),
    "PB-01": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-02": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-03": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-04": ("retained_external_runtime", "external_asset_required", "external_vendor_numeric_parity_unverified", "open_no_release"),
    "PB-05": ("retained_external_runtime", "external_asset_required", "external_vendor_numeric_parity_unverified", "open_no_release"),
    "COM-01": ("direct_rust_port", "unavailable", "scoped_observation", "open_no_release"),
    "COM-02": ("direct_rust_port", "external_asset_required", "scoped_numeric_mismatch_open", "open_no_release"),
    "COM-03": ("direct_rust_port", "unavailable", "scoped_observation", "open_no_release"),
    "COM-04": ("direct_rust_port", "external_asset_required", "scoped_numeric_mismatch_open", "open_no_release"),
}

FORMAL_EVIDENCE = {
    "AS-03": ("docs/baselines/as-03-power-wave-solve-replay.v1.yaml", "6f75c64caa30e2b49b1fc4851ddc5a9f8601687ae8028c11686cfc9da1e9ffa1"),
    "PB-01": ("docs/baselines/pb-01-02-portable-matrix.v1.yaml", "8029fedea415feeb52604d022b4fb7c437e532d938beb3788a6b7ffc23a35fed"),
    "PB-02": ("docs/baselines/pb-01-02-portable-matrix.v1.yaml", "8029fedea415feeb52604d022b4fb7c437e532d938beb3788a6b7ffc23a35fed"),
    "COM-01": ("com-01-fingerprint-current-replay-stage2.manifest.json", "893f31889ff2e9d736a90efcb8f6687c8aa81e78babcf85f0df543119cfe2a30"),
    "COM-03": ("docs/baselines/com-03-current-candidate-replay.v1.yaml", "2713a24151c802ef989dd6b3cb878c1ec0cf8b77031b6b68902e45bca1d6022c"),
}

FORMAL_SOURCES = {
    "as03_power_wave_replay": FORMAL_EVIDENCE["AS-03"],
    "pb_portable_matrix_formal": FORMAL_EVIDENCE["PB-01"],
    "com01_fingerprint_stage2": FORMAL_EVIDENCE["COM-01"],
    "com03_current_replay": FORMAL_EVIDENCE["COM-03"],
}

NEW_CHANGE_COMMITS = {
    "as03_power_wave_formal_record": COMMIT,
    "pb_portable_matrix_formal_record": "6a9b2cbe96eb51b4e406cb94be9ef11a3a487944",
    "com01_fingerprint_formal_record": "0743d86629c4813fc6da88d20da8df64bcb00730",
}

UPDATED_NONCLAIMS = {
    "AS-03": [
        "owner_retained_y_parameter_reference_only",
        "blocked_numeric_semantics",
        "four_real_bits_only",
        "max_one_ulp_is_not_acceptance",
        "no_numeric_parity",
        "no_global_parity",
        "no_product_capability_promotion",
        "no_release",
        "no_s_parameter_fit",
        "one_final_fd_to_td_impulse",
    ],
    "PB-01": [
        "scoped_matrix_only",
        "pb01_five_passed",
        "pb01_duo_binary_blocked",
        "pb02_six_cases_blocked",
        "no_numeric_parity",
        "no_global_branch_parity",
        "no_whole_payload_parity",
        "no_release",
    ],
    "PB-02": [
        "scoped_matrix_only",
        "pb02_six_cases_blocked",
        "no_numeric_parity",
        "no_global_branch_parity",
        "no_whole_payload_parity",
        "no_release",
    ],
    "COM-01": [
        "scoped_exact_fingerprint_only",
        "raw_sha256_per_replay_only",
        "no_complete_com_parity",
        "no_global_migration_row_close",
        "no_product_capability_promotion",
        "no_release_readiness",
        "no_configuration_value_payloads_committed",
        "no_s_parameter_fit",
        "channel_impulse_only_policy_unchanged",
        "no_canonical_pe_or_bit_reproducibility",
    ],
    "COM-03": [
        "scoped_current_candidate_only",
        "no_complete_com_parity",
        "no_global_migration_row_close",
        "no_product_capability_promotion",
        "no_release_readiness",
        "no_s_parameter_fit",
        "channel_impulse_only_policy_unchanged",
        "no_raw_result_payloads_in_evidence",
    ],
}

UPDATED_OBSERVATIONS = {
    "AS-03": {
        "formal_manifest": {"path": FORMAL_EVIDENCE["AS-03"][0], "sha256": FORMAL_EVIDENCE["AS-03"][1]},
        "audit": {"path": "docs/baselines/audits/2026-08-27-as-03-power-wave-solve-replay.md", "sha256": "975fb511fe5e39062c4a2020417f9bf533891b743f4573801fcee8a105776aac"},
        "status": "blocked_numeric_semantics",
        "comparison_scope": "committed 4 real bits vs pinned scikit-rf leaf",
        "real_bits": 4,
        "differing_real_bits": 3,
        "max_ulp": 1,
        "numeric_parity": False,
        "global_parity": False,
        "release_ready": False,
        "no_s_parameter_fit": True,
        "channel_policy": "one_final_fd_to_td_impulse",
    },
    "PB-01": {
        "formal_manifest": {"path": FORMAL_EVIDENCE["PB-01"][0], "sha256": FORMAL_EVIDENCE["PB-01"][1]},
        "audit": {"path": "docs/baselines/audits/pb-01-02-portable-matrix.audit.json", "sha256": "ff062f6790509ae2f89ccce4951074179bfcd5af013cc271521428db7702cb2b"},
        "status": "scoped_matrix_blocked",
        "fresh_replay_count": 2,
        "fresh_replays_consistent": True,
        "pb01_passed_case_count": 5,
        "pb01_duo_blocked": True,
        "pb02_blocked_case_count": 6,
        "numeric_parity": False,
        "global_branch_parity": False,
        "whole_payload_parity": False,
        "release_ready": False,
    },
    "PB-02": {
        "formal_manifest": {"path": FORMAL_EVIDENCE["PB-02"][0], "sha256": FORMAL_EVIDENCE["PB-02"][1]},
        "audit": {"path": "docs/baselines/audits/pb-01-02-portable-matrix.audit.json", "sha256": "ff062f6790509ae2f89ccce4951074179bfcd5af013cc271521428db7702cb2b"},
        "status": "scoped_matrix_blocked",
        "fresh_replay_count": 2,
        "fresh_replays_consistent": True,
        "pb01_passed_case_count": 5,
        "pb01_duo_blocked": True,
        "pb02_blocked_case_count": 6,
        "numeric_parity": False,
        "global_branch_parity": False,
        "whole_payload_parity": False,
        "release_ready": False,
    },
    "COM-01": {
        "formal_manifest": {"path": FORMAL_EVIDENCE["COM-01"][0], "sha256": FORMAL_EVIDENCE["COM-01"][1]},
        "audit": {"path": "docs/baselines/audits/2026-08-28-com-01-fingerprint-current-replay-stage2.md", "sha256": "4c2f041725735b4340cfe2d67c8dac1cf55d9486e442c9f462f4706f19f57360"},
        "status": "scoped_exact_materialized_fingerprint_stage2_formal_record",
        "fresh_replay_count": 2,
        "parity_claim": "scoped_exact_fingerprint_only",
        "binary_claim": "raw_sha256_per_replay_only",
        "acceptance": False,
        "complete_com_parity": False,
        "global_migration_row_closed": False,
        "product_capability_promoted": False,
        "release_ready": False,
        "no_s_parameter_fit": True,
        "channel_policy": "one_final_fd_to_td_impulse",
    },
    "COM-03": {
        "formal_manifest": {"path": FORMAL_EVIDENCE["COM-03"][0], "sha256": FORMAL_EVIDENCE["COM-03"][1]},
        "audit": {"path": "docs/baselines/audits/2026-08-27-com-03-current-candidate-replay.md", "sha256": "f024a2d4e78221b16aac3a35fc5a5cea3e778cc325b72bc411b14b038dd8972d"},
        "status": "scoped_current_candidate_observed",
        "scenario_count": 23,
        "matched_case_count": 23,
        "success_match_count": 7,
        "error_match_count": 16,
        "complete_com_parity": False,
        "global_migration_row_closed": False,
        "product_capability_promoted": False,
        "release_ready": False,
        "no_s_parameter_fit": True,
        "channel_policy": "one_final_fd_to_td_impulse",
    },
}


class LedgerError(RuntimeError):
    """Raised when a ledger assertion fails closed."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise LedgerError(reason)


def _exact_equal(actual: Any, expected: Any, reason: str) -> None:
    _require(type(actual) is type(expected), reason + "_type")
    if isinstance(expected, dict):
        _require(set(actual) == set(expected), reason + "_keys")
        for key in expected:
            _exact_equal(actual[key], expected[key], reason + ":" + str(key))
    elif isinstance(expected, list):
        _require(len(actual) == len(expected), reason + "_length")
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            _exact_equal(actual_item, expected_item, reason + ":" + str(index))
    else:
        _require(actual == expected, reason + "_value")


def _sha(path: Path, root: Path = ROOT) -> str:
    data = path.read_bytes()
    verifier = (root / "tools/verify_upstream_integration_ledger_v13.py").resolve()
    mutations = (root / MUTATION_TEST_PATH).resolve()
    if path.resolve() == verifier:
        data = re.sub(rb'EXPECTED_VERIFIER_SHA = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA = "<self>"', data, count=1)
        data = re.sub(rb'EXPECTED_MUTATION_SHA = "[0-9a-f]{64}"', b'EXPECTED_MUTATION_SHA = "<mutation>"', data, count=1)
    if path.resolve() == mutations:
        data = re.sub(rb'EXPECTED_VERIFIER_SHA256 = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA256 = "<verifier>"', data, count=1)
    return hashlib.sha256(data).hexdigest()


def _load(path: Path = LEDGER) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in tuple(env):
        if key.startswith("GIT_CONFIG_") or key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}:
            env.pop(key, None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _is_reparse(info: os.stat_result) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & flag)


def _safe(path: object, root: Path = ROOT) -> bool:
    if not isinstance(path, str) or not path:
        return False
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path) or "\\" in path:
        return False
    if ".." in path.split("/") or "temp" in path.lower():
        return False
    try:
        resolved_root = root.resolve(strict=True)
        target = (root / path).resolve(strict=True)
        target.relative_to(resolved_root)
        lexical = root / path
        current = root
        for component in lexical.relative_to(root).parts:
            current /= component
            info = current.lstat()
            if current.is_symlink() or _is_reparse(info):
                return False
        info = target.lstat()
        return stat.S_ISREG(info.st_mode) and getattr(info, "st_nlink", 1) == 1
    except (OSError, RuntimeError, ValueError):
        return False


def _bind(item: Any, reason: str, root: Path = ROOT) -> None:
    _require(type(item) is dict and set(item) == {"path", "sha256"}, reason + "_keys")
    _require(type(item["path"]) is str and type(item["sha256"]) is str and HEX64.fullmatch(item["sha256"]) is not None, reason + "_shape")
    _require(_safe(item["path"], root), reason + "_unsafe_path")
    target = root / item["path"]
    _require(target.is_file(), reason + "_missing")
    _require(_sha(target, root) == item["sha256"], reason + "_hash")


def _bind_tree(value: Any, reason: str, root: Path = ROOT) -> None:
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            _bind(value, reason, root)
        else:
            for key, child in value.items():
                _bind_tree(child, reason + ":" + str(key), root)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _bind_tree(child, reason + ":" + str(index), root)


def _declared_mutation_verifier_sha(root: Path = ROOT) -> str:
    text = (root / MUTATION_TEST_PATH).read_text(encoding="utf-8")
    match = re.search(r'^EXPECTED_VERIFIER_SHA256 = "([0-9a-f]{64})"$', text, re.MULTILINE)
    _require(match is not None, "mutation_verifier_anchor_shape")
    return match.group(1)


def _validate(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    expected_top = {"schema", "status", "successor", "candidate", "policy", "allowed_values", "source_authority", "change_commits", "current_sources", "rows", "summary", "plan", "audit", "harness"}
    _require(set(document) == expected_top, "top_keys")
    _exact_equal(document["schema"], SCHEMA, "schema")
    _exact_equal(document["status"], STATUS, "status")
    _exact_equal(document["successor"], {"predecessor": PREDECESSOR_PATH, "predecessor_sha256": PREDECESSOR_SHA, "reason": "additive v13 successor; v1-v12 remain immutable historical ledgers"}, "successor")
    _bind({"path": PREDECESSOR_PATH, "sha256": PREDECESSOR_SHA}, "predecessor", root)
    _exact_equal(document["candidate"], {"commit": COMMIT, "tree": TREE, "archive_sha256": ARCHIVE, "archive_bytes": ARCHIVE_BYTES, "materialization": "clean_git_archive", "autocrlf": True, "worktree_overlay": False}, "candidate")
    env = _git_env()
    tree = subprocess.run(["git", "-c", "core.autocrlf=true", "show", "-s", "--format=%T", COMMIT], cwd=root, env=env, capture_output=True, text=True, check=True).stdout.strip()
    _require(tree == TREE, "candidate_tree")
    archive = subprocess.run(["git", "-c", "core.autocrlf=true", "archive", "--format=tar", COMMIT], cwd=root, env=env, capture_output=True, check=True).stdout
    _require(len(archive) == ARCHIVE_BYTES and hashlib.sha256(archive).hexdigest() == ARCHIVE, "candidate_archive")
    expected_policy = {"new_domain_features_allowed": False, "direct_rust_port_requires_named_upstream_behavior": True, "external_runtime_is_not_parity": True, "scoped_observation_is_not_global_parity": True, "release_promotion_requires_branch_complete_evidence": True, "s_parameter_fit": "forbidden", "channel_policy": "one_final_fd_to_td_impulse"}
    _exact_equal(document["policy"], expected_policy, "policy")
    expected_allowed = {"integration_disposition": ["direct_rust_port", "retained_external_runtime", "external_asset", "oracle_only", "excluded_fail_closed"], "runtime_availability": ["portable", "external_solver_required", "external_asset_required", "unavailable"], "parity_evidence": ["scoped_numeric_mismatch_open", "scoped_observation", "numeric_observation", "external_blocker_observed", "external_solver_not_verified", "external_vendor_numeric_parity_unverified", "upstream_only_timeout", "historical_only"], "release_state": ["open_no_release", "scoped_only_no_release", "excluded_no_release"]}
    _exact_equal(document["allowed_values"], expected_allowed, "allowed_values")
    predecessor = _load(root / PREDECESSOR_PATH)
    expected_changes = dict(predecessor["change_commits"])
    expected_changes.update(NEW_CHANGE_COMMITS)
    _exact_equal(document["change_commits"], expected_changes, "change_commits")
    _require(all(HEX40.fullmatch(value) for value in document["change_commits"].values()), "change_commit_shape")
    expected_sources = dict(predecessor["current_sources"])
    expected_sources["com01_source_map"]["sha256"] = "ec424d0cf8f407d35696011ddc5751f5c147dd02d0769226e4784f60130fc326"
    expected_sources.update({name: {"path": path, "sha256": sha} for name, (path, sha) in FORMAL_SOURCES.items()})
    _exact_equal(document["current_sources"], expected_sources, "current_sources")
    _bind_tree(document["current_sources"], "current_sources", root)
    previous_rows = {row["id"]: row for row in predecessor["rows"]}
    _require(len(document["rows"]) == 15 and len(previous_rows) == 15, "row_count")
    for row, (row_id, repo, entry) in zip(document["rows"], ROWS):
        _require(isinstance(row, dict), "row_shape:" + row_id)
        _exact_equal([row.get("id"), row.get("repo"), row.get("public_entrypoint")], [row_id, repo, entry], "row_identity:" + row_id)
        _exact_equal([row.get(key) for key in ("integration_disposition", "runtime_availability", "parity_evidence", "release_state")], list(POLICY[row_id]), "row_policy:" + row_id)
        expected_evidence = {"path": FORMAL_EVIDENCE[row_id][0], "sha256": FORMAL_EVIDENCE[row_id][1]} if row_id in FORMAL_EVIDENCE else previous_rows[row_id]["evidence"]
        _exact_equal(row.get("evidence"), expected_evidence, "evidence_exact:" + row_id)
        _bind(row["evidence"], "evidence:" + row_id, root)
        if row_id not in UPDATED_NONCLAIMS:
            _exact_equal(row, previous_rows[row_id], "row_preserved:" + row_id)
            continue
        _exact_equal(row.get("non_claims"), UPDATED_NONCLAIMS[row_id], "nonclaims:" + row_id)
        _exact_equal(row.get("current_observation"), UPDATED_OBSERVATIONS[row_id], "observation_exact:" + row_id)
        _bind_tree(row["current_observation"], "observation:" + row_id, root)
    _exact_equal(document["summary"], {"rows": 15, "direct_rust_port": 10, "retained_external_runtime": 3, "external_asset": 0, "oracle_only": 0, "excluded_fail_closed": 2, "release_ready": 0}, "summary")
    _exact_equal(document["plan"], {"path": PLAN_PATH, "sha256": EXPECTED_PLAN_SHA}, "plan")
    _bind(document["plan"], "plan", root)
    plan_text = (root / PLAN_PATH).read_text(encoding="utf-8")
    for marker in (PLAN_MARKER, "upstream-integration-ledger.v13", "189ffaa85f8f21ae7cdc7b2ca8f126122d9b335f", "15/15 rows", "release-ready=0", "AS-05", "owner_excluded_not_required", "Xyce/XDM", "S 参数", "one-final FD-to-TD impulse", "row close"):
        _require(marker in plan_text, "plan_marker:" + marker)
    _exact_equal(document["audit"], {"path": AUDIT_PATH, "sha256": EXPECTED_AUDIT_SHA}, "audit")
    _bind(document["audit"], "audit", root)
    audit_text = (root / AUDIT_PATH).read_text(encoding="utf-8")
    for marker in (PLAN_MARKER, SCHEMA, COMMIT, TREE, ARCHIVE, "15 migration rows", "release-ready=0", "blocked_numeric_semantics", "scoped_matrix_blocked", "scoped_exact_materialized_fingerprint_stage2_formal_record", "scoped_current_candidate_observed", "owner_excluded_not_required", "Xyce/XDM", "No row is closed"):
        _require(marker in audit_text, "audit_marker:" + marker)
    expected_harness = {"verifier": {"path": "tools/verify_upstream_integration_ledger_v13.py", "sha256": EXPECTED_VERIFIER_SHA}, "mutation_tests": {"path": MUTATION_TEST_PATH, "sha256": EXPECTED_MUTATION_SHA}}
    _exact_equal(document["harness"], expected_harness, "harness")
    _bind(document["harness"]["verifier"], "harness_verifier", root)
    _bind(document["harness"]["mutation_tests"], "harness_mutations", root)
    _require(_declared_mutation_verifier_sha(root) == EXPECTED_VERIFIER_SHA, "mutation_verifier_anchor")
    _require(EXPECTED_VERIFIER_SHA == _sha(root / "tools/verify_upstream_integration_ledger_v13.py", root), "verifier_self_anchor")
    _require(EXPECTED_MUTATION_SHA == _sha(root / MUTATION_TEST_PATH, root), "mutation_self_anchor")
    return {"valid": True, "rows": 15, "release_ready": 0}


def validate(document: dict[str, Any], repo_root: Path = ROOT) -> dict[str, Any]:
    try:
        return _validate(document, repo_root)
    except LedgerError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        raise LedgerError("malformed:" + type(exc).__name__) from None


if __name__ == "__main__":
    print(validate(_load()))
