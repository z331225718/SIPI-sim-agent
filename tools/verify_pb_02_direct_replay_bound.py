"""Verify additive PB-02 immutable direct-replay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "pb-02-direct-replay-bound.v2.yaml"
EXPECTED_SCHEMA = "sipi.pb-02-direct-replay-bound.v2"
EXPECTED_STATUS = "accepted_scoped_native_core_bound_open"
REPORT_SCHEMA = "sipi.pb-02-direct-replay.v1"
AGGREGATE_SCHEMA = "sipi.pb-02-direct-replay-aggregate.v1"
EXPECTED_COMMIT = "ec94468772182e17cf7b935ab2d7c0437ea7692e"
EXPECTED_TREE = "5e0de1ac29f64f935339a4d5eed09fc1b43c6591"
EXPECTED_CANDIDATE_ARCHIVE = "ac09b63467b13aad97c035f0c165f5c5f3725d0f36247a6b5ca2eb257682e27e"
EXPECTED_CANDIDATE_INVENTORY = "f552c0b0bfe971d7f8b94123cdcb78cb798c18ca8ec7ccd9a832241c4a3731cc"
EXPECTED_CARGO_LOCK = "9f282c66d2fecaec3e6dc1cd32d0d61dc2bb19da71c21ac1d1a3507378b443ee"
EXPECTED_RUST_TOOLCHAIN = "3cc13c37191008eaab5490eea2136223fa1bc5b5d2aa9c74a199a0c0c854aa90"
EXPECTED_UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
EXPECTED_UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
EXPECTED_UPSTREAM_ARCHIVE = "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25"
EXPECTED_UPSTREAM_INVENTORY = "26ccbee692b9c4984c6cee0cff6c3987fc013e914905a66019937f940a5abfb9"
EXPECTED_LICENSE = "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1"
EXPECTED_UV_LOCK = "624b62d7a84fbc48579de17e2ae171f5e4190d6ad7e5231e67ddafb9d3fa0d86"
EXPECTED_FIXTURE_PATH = "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json"
EXPECTED_FIXTURE_BYTES = 1245
EXPECTED_FIXTURE_SHA = "5bcd0b905f8a7f0ec5e2b7c3761a998e9553ac24a71b54f8b0d4e8e84261ea13"
EXPECTED_RUNNER = (
    "tools/run_pb_02_direct_replay.py",
    "6c6a777a2e616e5778eaa7f396ba173791c67381d81cf00b473f87efb2553d0f",
)
EXPECTED_AGGREGATOR = (
    "tools/aggregate_pb_02_direct_replay.py",
    "04a2d35fd7f1df1fc3728c0918fc752980b0e7c718eedf5a0285ff0bae24043a",
)
EXPECTED_AUDIT = (
    "docs/baselines/audits/2026-08-23-pb-02-direct-replay-bound.md",
    "",
)
EXPECTED_REPORTS = {
    "first": {
        "path": "docs/baselines/pb-02-direct-replay-bound-run-01.v1.json",
        "sha256": "3899be3eec0c561fe0526d71dd7f0c78f1d9e872334595fef7ebcdfddc149096",
        "run_id": "pb-02-bound-20260823-01",
        "fresh_run_nonce": "5a37eedb1b9c36c1f616125296d97be92ec386bd26dc450545eef3d1b5537711",
    },
    "second": {
        "path": "docs/baselines/pb-02-direct-replay-bound-run-02.v1.json",
        "sha256": "737b6a042f4251e380a3e66cf31089a3b28ba16e67c459ea7c4ab4915e8c3a6d",
        "run_id": "pb-02-bound-20260823-02",
        "fresh_run_nonce": "ff6a5f87048ab409a6b3eedb4628cf69f74eb8af4efef9703ea71e61c71e976b",
    },
}
EXPECTED_AGGREGATE = (
    "docs/baselines/pb-02-direct-replay-bound-aggregate.v1.json",
    "ada25b3ea02cf98f7290cbea77192f46bd8f8043b4d3b7fa44cf8915d9197ab2",
)
EXPECTED_LOGICAL_SHA = "5090a1478ea6e985342d8500c6220cdde5c7fa2c416abbdeb595dcdc380c275a"
EXPECTED_LOGICAL_MEMBERS: dict[str, dict[str, Any]] = {
    "channel_impulse_v_per_v.npy": {
        "count": 2,
        "dtype": "<f8",
        "shape": [2],
        "fortran_order": False,
        "f64_sha256": "82d5182c90ecefa00f9e9d91f02ad8be6d9d082f377bd1f96c00f010bc053e36",
    },
    "channel_output_v.npy": {
        "count": 32,
        "dtype": "<f8",
        "shape": [32],
        "fortran_order": False,
        "f64_sha256": "bbe26fb833fd898ba1033701957b0cace8d7387a22d0518f9404630406013309",
    },
    "ctle_output_v.npy": {
        "count": 32,
        "dtype": "<f8",
        "shape": [32],
        "fortran_order": False,
        "f64_sha256": "bbe26fb833fd898ba1033701957b0cace8d7387a22d0518f9404630406013309",
    },
    "rx_ffe_impulse_v_per_v.npy": {
        "count": 32,
        "dtype": "<f8",
        "shape": [32],
        "fortran_order": False,
        "f64_sha256": "8034367eec76495180b08e634d0bf4236b83a30d9ce7be3fd843fe8860f4de41",
    },
    "rx_filter_impulse_v_per_v.npy": {
        "count": 1,
        "dtype": "<f8",
        "shape": [1],
        "fortran_order": False,
        "f64_sha256": "6c3c396ed6b5c36dcae172271f462051b1266b851e92df3deea8ac65478fd712",
    },
    "rx_input_v.npy": {
        "count": 32,
        "dtype": "<f8",
        "shape": [32],
        "fortran_order": False,
        "f64_sha256": "bbe26fb833fd898ba1033701957b0cace8d7387a22d0518f9404630406013309",
    },
    "rx_output_v.npy": {
        "count": 32,
        "dtype": "<f8",
        "shape": [32],
        "fortran_order": False,
        "f64_sha256": "bbe26fb833fd898ba1033701957b0cace8d7387a22d0518f9404630406013309",
    },
    "symbols_v.npy": {
        "count": 16,
        "dtype": "<f8",
        "shape": [16],
        "fortran_order": False,
        "f64_sha256": "6884fb21aa1699022a9207c5cfeecc8d67d10e93d698ad6e7e2ee75e5c47c365",
    },
    "time_s.npy": {
        "count": 32,
        "dtype": "<f8",
        "shape": [32],
        "fortran_order": False,
        "f64_sha256": "58bbee68c5a97e80d59296425c4726ebeabe38d848dc055134fb4a65f6d2b6b2",
    },
    "tx_channel_impulse_v_per_v.npy": {
        "count": 2,
        "dtype": "<f8",
        "shape": [2],
        "fortran_order": False,
        "f64_sha256": "82d5182c90ecefa00f9e9d91f02ad8be6d9d082f377bd1f96c00f010bc053e36",
    },
    "tx_waveform_v.npy": {
        "count": 32,
        "dtype": "<f8",
        "shape": [32],
        "fortran_order": False,
        "f64_sha256": "40b756e3bbe3ed90ade86b60c2f4d51764cd4033b577629835076308de2c1a35",
    },
}
EXPECTED_TOOLCHAIN: dict[str, Any] = {
    "timeout_seconds": 1200,
    "cargo": {
        "role": "cargo",
        "executable": "cargo.exe",
        "path_redacted": True,
        "file_sha256": "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7",
        "version_exit_code": 0,
        "version_output_sha256": "4e9216fb7cac2573c1a8d60be140200103a52ab9fd9415070d94a98b1ef5973a",
    },
    "rustc": {
        "role": "rustc",
        "executable": "rustc.exe",
        "path_redacted": True,
        "file_sha256": "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7",
        "version_exit_code": 0,
        "version_output_sha256": "d6dec673ca010f6a7d90aa3f4a896ad9d88b66b8fe090296c298eddfe9a406db",
    },
    "uv": {
        "role": "uv",
        "executable": "uv.exe",
        "path_redacted": True,
        "file_sha256": "cd628b46729d01ad110146a647a633a6e5de0e091d73db46afaeee6fcb4ba648",
        "version_exit_code": 0,
        "version_output_sha256": "6811b26ed08e84a0a753846eb4784e33181cb77ceaf9b7cee4ac35af9b2ed001",
    },
}
EXPECTED_AUDIT_PATH = EXPECTED_AUDIT[0]
EXPECTED_NON_CLAIMS = {
    "This evidence covers only the explicit PB-02 fixture and not every SimulationInputV1 branch.",
    "SIPI strict JSON, artifact, NPZ, and symlink policies are wrapper behavior, not upstream sim-native semantics.",
    "This evidence is not a license decision, release approval, or product capability admission.",
}
PATH_LEAK_RE = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        return _sha256(path.read_bytes())
    except OSError:
        return None


def _check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def _repo_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def _check_path_value(blockers: list[str], value: Any, label: str) -> None:
    _check(blockers, _repo_relative(value), f"{label} must be a repository-relative POSIX path")


def _verify_path_free(value: Any, blockers: list[str], label: str) -> None:
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    _check(blockers, PATH_LEAK_RE.search(serialized) is None, f"{label} contains an absolute host path")


def _verify_digest_file(
    root: Path, relative: Any, expected: str, blockers: list[str], label: str
) -> None:
    _check_path_value(blockers, relative, label + " path")
    if not _repo_relative(relative):
        return
    actual = _sha256_file(root / relative)
    _check(blockers, actual == expected, f"{label} hash drift")


def _verify_toolchain(value: Any, blockers: list[str], label: str) -> None:
    _check(blockers, isinstance(value, dict), f"{label} missing")
    if not isinstance(value, dict):
        return
    _check(blockers, set(value) == set(EXPECTED_TOOLCHAIN), f"{label} key set drift")
    _check(blockers, value.get("timeout_seconds") == EXPECTED_TOOLCHAIN["timeout_seconds"], f"{label} timeout drift")
    for role in ("cargo", "rustc", "uv"):
        item = value.get(role)
        expected = EXPECTED_TOOLCHAIN[role]
        _check(blockers, isinstance(item, dict), f"{label}.{role} missing")
        if not isinstance(item, dict):
            continue
        _check(blockers, set(item) == set(expected), f"{label}.{role} key set drift")
        _check(blockers, item == expected, f"{label}.{role} identity drift")
        _check(blockers, item.get("path_redacted") is True, f"{label}.{role} path is not redacted")
        _check(blockers, isinstance(item.get("executable"), str) and "/" not in item.get("executable", "") and "\\" not in item.get("executable", ""), f"{label}.{role} executable path leak")


def _verify_identity(
    value: Any,
    expected: dict[str, Any],
    blockers: list[str],
    label: str,
) -> None:
    _check(blockers, isinstance(value, dict), f"{label} missing")
    if not isinstance(value, dict):
        return
    for key, expected_value in expected.items():
        _check(blockers, value.get(key) == expected_value, f"{label}.{key} drift")


def _verify_logical_members(value: Any, blockers: list[str], label: str) -> None:
    _check(blockers, isinstance(value, dict), f"{label} missing")
    if not isinstance(value, dict):
        return
    _check(blockers, set(value) == set(EXPECTED_LOGICAL_MEMBERS), f"{label} member set drift")
    for name, expected in EXPECTED_LOGICAL_MEMBERS.items():
        item = value.get(name)
        _check(blockers, item == expected, f"{label}.{name} digest drift")


def _verify_report(root: Path, report: dict[str, Any], blockers: list[str], label: str) -> None:
    _check(blockers, isinstance(report, dict), f"{label} JSON is not an object")
    if not isinstance(report, dict):
        return
    _check(blockers, report.get("schema") == REPORT_SCHEMA, f"{label} schema drift")
    _check(blockers, report.get("status") == "passed", f"{label} status drift")
    _check(blockers, report.get("source_mode") == "git_archive_at_immutable_commit", f"{label} source mode drift")
    _verify_toolchain(report.get("toolchain"), blockers, f"{label}.toolchain")
    _verify_path_free(report, blockers, label)
    candidate = report.get("candidate")
    _verify_identity(
        candidate,
        {
            "commit": EXPECTED_COMMIT,
            "tree": EXPECTED_TREE,
            "archive_sha256": EXPECTED_CANDIDATE_ARCHIVE,
            "cargo_lock_sha256": EXPECTED_CARGO_LOCK,
            "rust_toolchain_sha256": EXPECTED_RUST_TOOLCHAIN,
        },
        blockers,
        f"{label}.candidate",
    )
    if isinstance(candidate, dict):
        inventory = candidate.get("inventory")
        _check(blockers, isinstance(inventory, dict), f"{label}.candidate inventory missing")
        if isinstance(inventory, dict):
            _check(blockers, inventory.get("sha256") == EXPECTED_CANDIDATE_INVENTORY, f"{label}.candidate inventory hash drift")
            _check_path_value(blockers, next((entry.get("path") for entry in inventory.get("entries", []) if isinstance(entry, dict)), ""), f"{label}.candidate inventory entry")
    _verify_identity(
        report.get("upstream"),
        {
            "commit": EXPECTED_UPSTREAM_COMMIT,
            "tree": EXPECTED_UPSTREAM_TREE,
            "archive_sha256": EXPECTED_UPSTREAM_ARCHIVE,
            "license_sha256": EXPECTED_LICENSE,
            "native_core_cargo_lock_sha256": None,
            "uv_lock_sha256": EXPECTED_UV_LOCK,
        },
        blockers,
        f"{label}.upstream",
    )
    _verify_identity(
        report.get("fixture"),
        {"path": EXPECTED_FIXTURE_PATH, "bytes": EXPECTED_FIXTURE_BYTES, "sha256": EXPECTED_FIXTURE_SHA},
        blockers,
        f"{label}.fixture",
    )
    if isinstance(report.get("fixture"), dict):
        _check_path_value(blockers, report["fixture"].get("path"), f"{label}.fixture")
    replay = report.get("replay")
    _check(blockers, isinstance(replay, dict), f"{label}.replay missing")
    if not isinstance(replay, dict):
        return
    parity = replay.get("parity")
    _check(blockers, isinstance(parity, dict), f"{label}.parity missing")
    if isinstance(parity, dict):
        _check(blockers, parity.get("candidate_exit_zero") is True, f"{label} candidate exit drift")
        _check(blockers, parity.get("oracle_exit_zero") is True, f"{label} oracle exit drift")
        _check(blockers, parity.get("candidate_array_members_equal_oracle") is True, f"{label} array parity drift")
    for side in ("candidate", "oracle"):
        side_value = replay.get(side)
        _check(blockers, isinstance(side_value, dict), f"{label}.{side} replay missing")
        if not isinstance(side_value, dict):
            continue
        _check(blockers, side_value.get("exit_code") == 0, f"{label}.{side} exit drift")
        artifacts = side_value.get("artifacts")
        _check(blockers, isinstance(artifacts, dict), f"{label}.{side} artifacts missing")
        if not isinstance(artifacts, dict):
            continue
        _check(blockers, artifacts.get("meta_schema") == "pybert.native-cli-result.v1", f"{label}.{side} meta schema drift")
        for key in ("meta_present", "meta_json_valid", "arrays_present"):
            _check(blockers, artifacts.get(key) is True, f"{label}.{side} {key} drift")
        arrays = artifacts.get("arrays")
        _check(blockers, isinstance(arrays, dict), f"{label}.{side} arrays missing")
        if isinstance(arrays, dict):
            _check(blockers, arrays.get("logical_sha256") == EXPECTED_LOGICAL_SHA, f"{label}.{side} logical array hash drift")
            _verify_logical_members(arrays.get("logical_members"), blockers, f"{label}.{side} logical members")


def _load_json(root: Path, relative: str, blockers: list[str], label: str) -> dict[str, Any] | None:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        blockers.append(f"{label} cannot be loaded: {exc}")
        return None
    if not isinstance(value, dict):
        blockers.append(f"{label} JSON is not an object")
        return None
    return value


def _verify_reports(root: Path, document: dict[str, Any], blockers: list[str]) -> list[dict[str, Any]]:
    reports = document.get("reports")
    _check(blockers, isinstance(reports, dict) and set(reports) == set(EXPECTED_REPORTS), "report binding key set drift")
    if not isinstance(reports, dict):
        return []
    loaded: list[dict[str, Any]] = []
    for name, expected in EXPECTED_REPORTS.items():
        item = reports.get(name)
        _check(blockers, isinstance(item, dict), f"report binding missing: {name}")
        if not isinstance(item, dict):
            continue
        _check(blockers, item == expected, f"report binding drift: {name}")
        _verify_digest_file(root, item.get("path"), expected["sha256"], blockers, f"report {name}")
        if _repo_relative(item.get("path")):
            report = _load_json(root, item["path"], blockers, f"report {name}")
            if report is not None:
                _verify_report(root, report, blockers, f"report {name}")
                _check(blockers, report.get("run_id") == expected["run_id"], f"report {name} run id drift")
                _check(blockers, report.get("fresh_run_nonce") == expected["fresh_run_nonce"], f"report {name} fresh nonce drift")
                loaded.append(report)
    return loaded


def _verify_aggregate(root: Path, document: dict[str, Any], blockers: list[str]) -> None:
    aggregate = document.get("aggregate")
    _check(blockers, isinstance(aggregate, dict), "aggregate binding missing")
    if not isinstance(aggregate, dict):
        return
    _check(blockers, aggregate == {"path": EXPECTED_AGGREGATE[0], "sha256": EXPECTED_AGGREGATE[1]}, "aggregate binding drift")
    _verify_digest_file(root, aggregate.get("path"), EXPECTED_AGGREGATE[1], blockers, "aggregate")
    if not _repo_relative(aggregate.get("path")):
        return
    value = _load_json(root, aggregate["path"], blockers, "aggregate")
    if value is None:
        return
    _check(blockers, value.get("schema") == AGGREGATE_SCHEMA, "aggregate schema drift")
    _check(blockers, value.get("status") == "passed", "aggregate status drift")
    _check(blockers, value.get("blockers") == [], "aggregate blockers are nonempty")
    _verify_toolchain(value.get("toolchain"), blockers, "aggregate.toolchain")
    _verify_path_free(value, blockers, "aggregate")
    _verify_identity(value.get("candidate"), {"commit": EXPECTED_COMMIT, "tree": EXPECTED_TREE, "archive_sha256": EXPECTED_CANDIDATE_ARCHIVE, "cargo_lock_sha256": EXPECTED_CARGO_LOCK, "rust_toolchain_sha256": EXPECTED_RUST_TOOLCHAIN}, blockers, "aggregate.candidate")
    _verify_identity(value.get("upstream"), {"commit": EXPECTED_UPSTREAM_COMMIT, "tree": EXPECTED_UPSTREAM_TREE, "archive_sha256": EXPECTED_UPSTREAM_ARCHIVE, "license_sha256": EXPECTED_LICENSE, "native_core_cargo_lock_sha256": None, "uv_lock_sha256": EXPECTED_UV_LOCK}, blockers, "aggregate.upstream")
    _verify_identity(value.get("fixture"), {"path": EXPECTED_FIXTURE_PATH, "bytes": EXPECTED_FIXTURE_BYTES, "sha256": EXPECTED_FIXTURE_SHA}, blockers, "aggregate.fixture")
    if isinstance(value.get("fixture"), dict):
        _check_path_value(blockers, value["fixture"].get("path"), "aggregate.fixture")
    _check(blockers, value.get("logical_array_member_sha256") == EXPECTED_LOGICAL_MEMBERS, "aggregate logical member digest drift")
    entries = value.get("reports")
    expected_entries = [
        {"path": item["path"], "sha256": item["sha256"], "run_id": item["run_id"], "fresh_run_nonce": item["fresh_run_nonce"], "logical_array_sha256": EXPECTED_LOGICAL_SHA}
        for item in EXPECTED_REPORTS.values()
    ]
    _check(blockers, entries == expected_entries, "aggregate report list drift")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                _check_path_value(blockers, entry.get("path"), "aggregate report")


def _verify_distinct_gate(document: dict[str, Any], blockers: list[str]) -> None:
    expected = {
        "unique_resolved_report_paths": True,
        "unique_report_sha256": True,
        "unique_run_ids": True,
        "unique_fresh_run_nonces": True,
        "exact_toolchain_identity_across_runs": True,
        "path_free_report_identity": True,
    }
    _check(blockers, document.get("distinct_gate") == expected, "distinct gate drift")


def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    _check(blockers, isinstance(document, dict), "evidence is not a mapping")
    if not isinstance(document, dict):
        return {"valid": False, "blockers": blockers}
    _check(blockers, document.get("schema") == EXPECTED_SCHEMA, "schema drift")
    _check(blockers, document.get("status") == EXPECTED_STATUS, "status drift")
    scope = document.get("scope")
    _check(blockers, isinstance(scope, dict), "scope missing")
    if isinstance(scope, dict):
        for key, expected in {
            "workflow": "PB-02",
            "command": "sim-native",
            "lane_crate": "crates/sipi-pybert-direct",
            "replay_mode": "immutable_candidate_and_pinned_upstream_archive",
            "exact_native_core_numerical_replay_only": True,
            "product_capability_promoted": False,
            "global_migration_row_closed": False,
            "release_ready": False,
        }.items():
            _check(blockers, scope.get(key) == expected, f"scope drift: {key}")
    _verify_identity(document.get("candidate"), {"commit": EXPECTED_COMMIT, "tree": EXPECTED_TREE, "archive_sha256": EXPECTED_CANDIDATE_ARCHIVE, "inventory_sha256": EXPECTED_CANDIDATE_INVENTORY, "cargo_lock_sha256": EXPECTED_CARGO_LOCK, "rust_toolchain_sha256": EXPECTED_RUST_TOOLCHAIN}, blockers, "candidate")
    _verify_identity(document.get("upstream"), {"repository": "pybert", "commit": EXPECTED_UPSTREAM_COMMIT, "tree": EXPECTED_UPSTREAM_TREE, "archive_sha256": EXPECTED_UPSTREAM_ARCHIVE, "inventory_sha256": EXPECTED_UPSTREAM_INVENTORY, "license_sha256": EXPECTED_LICENSE, "native_core_cargo_lock_sha256": None, "uv_lock_sha256": EXPECTED_UV_LOCK}, blockers, "upstream")
    _verify_identity(document.get("fixture"), {"path": EXPECTED_FIXTURE_PATH, "bytes": EXPECTED_FIXTURE_BYTES, "sha256": EXPECTED_FIXTURE_SHA}, blockers, "fixture")
    if isinstance(document.get("fixture"), dict):
        _check_path_value(blockers, document["fixture"].get("path"), "fixture")
    _verify_digest_file(root, EXPECTED_FIXTURE_PATH, EXPECTED_FIXTURE_SHA, blockers, "fixture file")
    for key, expected in (("replay_runner", EXPECTED_RUNNER), ("aggregate_runner", EXPECTED_AGGREGATOR)):
        item = document.get(key)
        _check(blockers, isinstance(item, dict) and item == {"path": expected[0], "sha256": expected[1]}, f"{key} binding drift")
        if isinstance(item, dict):
            _verify_digest_file(root, item.get("path"), expected[1], blockers, key)
    _verify_toolchain(document.get("toolchain"), blockers, "evidence.toolchain")
    _verify_distinct_gate(document, blockers)
    _check(blockers, document.get("logical_arrays", {}).get("sha256") == EXPECTED_LOGICAL_SHA if isinstance(document.get("logical_arrays"), dict) else False, "logical array root digest drift")
    if isinstance(document.get("logical_arrays"), dict):
        _verify_logical_members(document["logical_arrays"].get("members"), blockers, "evidence logical members")
    wrapper = document.get("wrapper_boundary")
    _check(blockers, wrapper == {"strict_json_admission": "sipi_owned_non_parity", "artifact_writer": "sipi_owned_non_parity", "uncompressed_npz_writer": "sipi_owned_non_parity", "output_directory_symlink_rejection": "sipi_owned_non_parity", "upstream_native_parity_scope": "excluded"}, "wrapper boundary drift")
    claims = document.get("claims")
    _check(blockers, claims == {"exact_native_core_numerical_parity_for_fixture": True, "uncovered_input_branches_open": True, "license_decision": False, "product_capability_admission": False, "release_approval": False}, "claim boundary drift")
    _check(blockers, set(document.get("non_claims", [])) == EXPECTED_NON_CLAIMS, "non-claim boundary drift")
    audit = document.get("audit")
    _check(blockers, isinstance(audit, dict), "audit binding missing")
    if isinstance(audit, dict):
        _check(blockers, audit.get("path") == EXPECTED_AUDIT_PATH, "audit path binding drift")
        _check_path_value(blockers, audit.get("path"), "audit")
        audit_sha = _sha256_file(root / EXPECTED_AUDIT_PATH)
        _check(blockers, audit.get("sha256") == audit_sha and isinstance(audit_sha, str) and len(audit_sha) == 64, "audit hash binding drift")
    _verify_path_free(document, blockers, "evidence")
    loaded_reports = _verify_reports(root, document, blockers)
    if len(loaded_reports) == 2:
        _check(blockers, loaded_reports[0].get("fresh_run_nonce") != loaded_reports[1].get("fresh_run_nonce"), "fresh nonces are not distinct")
        _check(blockers, loaded_reports[0].get("run_id") != loaded_reports[1].get("run_id"), "run ids are not distinct")
    _verify_aggregate(root, document, blockers)
    return {"valid": not blockers, "blockers": blockers, "reports": len(loaded_reports)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.evidence.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(json.dumps({"valid": False, "blockers": [str(exc)]}, indent=2))
        return 1
    result = verify(document, args.evidence.resolve().parents[2])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
