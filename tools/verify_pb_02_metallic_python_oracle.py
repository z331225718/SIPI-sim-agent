"""Fail-closed verifier for the PB-02 replay prep contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "docs/baselines/pb-02-metallic-python-oracle-corpus.v1.json"
MANIFEST = ROOT / "docs/baselines/pb-02-metallic-python-oracle.v1.yaml"
EXPECTED_CANDIDATE = {
    "commit": "dc82489d109f27b70940a5f1037cb08d3c10a8b6",
    "tree": "6311d5a0e88cd008e22ab9dcc0e7c18f57120ed3",
    "archive_sha256": "dcf9e38aaf0980c40a6c7640e5c229ac851a11e7c287d4bde386b21b1e9c5b00",
}
EXPECTED_UPSTREAM = {
    "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
    "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
    "archive_sha256": "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25",
}
EXPECTED_SOURCE_MODE = "git_archive_at_candidate_prep_commit_plus_content_addressed_input_corpus_and_harness_snapshot"
EXPECTED_CASES = ["metallic-ctle-ordinary-3ghz-10ghz", "metallic-ctle-near-integral-3ghz"]
EXPECTED_FIELDS = [
    "channel_impulse_v_per_v", "channel_output_v", "legacy_channel_frequency_hz",
    "legacy_channel_raw_re", "legacy_channel_raw_im", "legacy_channel_terminated_re",
    "legacy_channel_terminated_im", "legacy_channel_trimmed_re", "legacy_channel_trimmed_im",
    "rx_filter_impulse_v_per_v", "legacy_stage_ctle_re", "legacy_stage_ctle_im",
    "legacy_stage_ctle_out_re", "legacy_stage_ctle_out_im", "ctle_output_v", "rx_output_v", "dfe_output_v",
]
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")
HARNESS_PATHS = [
    "tools/run_pb_03_python_oracle_matrix.py", "tools/pb_02_metallic_python_oracle.py",
    "tools/run_pb_02_metallic_python_oracle.py", "tools/aggregate_pb_02_metallic_python_oracle.py",
    "tools/verify_pb_02_metallic_python_oracle.py", "tools/test_verify_pb_02_metallic_python_oracle.py",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(value: Any) -> bool:
    return isinstance(value, str) and not Path(value).is_absolute() and ".." not in Path(value).parts and "\\" not in value


def _check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def _policies() -> dict[str, dict[str, Any]]:
    return {
        EXPECTED_CASES[0]: {"candidate_exit_code": 0, "oracle_exit_code": 0, "compared_field_count": 17, "require_payload_parity": True},
        EXPECTED_CASES[1]: {
            "candidate_exit_code": 0, "oracle_exit_code": 1, "compared_field_count": 0,
            "require_payload_parity": False,
            "oracle_failure_code": "pinned_channel_cubic_interp1d_two_point_boundary",
            "oracle_failure_stage": "channel",
        },
    }


def _claims() -> dict[str, Any]:
    return {
        "ordinary_payload_parity": False, "near_integral_external_blocked": False,
        "near_integral_counted_as_parity": False, "global_branch_parity": False, "promotion": False,
    }


def prep_document(root: Path = ROOT) -> dict[str, Any]:
    corpus_payload = CORPUS.read_bytes()
    corpus = json.loads(corpus_payload.decode("utf-8"))
    fixture_path = str(corpus["base_fixture"])
    return {
        "schema": "sipi.pb-02-metallic-python-oracle-prep.v2", "version": 2,
        "status": "prep_only_no_formal_replay", "row": "PB-02",
        "scope": "analytic_ctle_metallic_noninteger_grid", "source_mode": EXPECTED_SOURCE_MODE,
        "candidate": EXPECTED_CANDIDATE, "upstream": EXPECTED_UPSTREAM,
        "corpus": {
            "path": "docs/baselines/pb-02-metallic-python-oracle-corpus.v1.json", "sha256": digest(CORPUS),
            "base_fixture": fixture_path, "base_fixture_sha256": digest(root / fixture_path),
            "case_ids": EXPECTED_CASES, "expected_fields": EXPECTED_FIELDS,
        },
        "harness": {path: {"path": path, "sha256": digest(root / path)} for path in HARNESS_PATHS},
        "toolchain_contract": {
            "required_roles": ["cargo", "rustc", "uv", "python"], "path_redacted": True,
            "required_keys": ["role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"],
            "child_python_required_keys": ["command", "process", "identity"],
            "child_python_identity_keys": ["python", "numpy", "scipy"],
            "child_python_executable_keys": ["executable", "file_sha256", "implementation", "version", "path_redacted"],
            "host_python_required_keys": ["executable", "file_sha256", "path_redacted", "source"],
            "version_exit_code": 0,
        },
        "build_contract": {
            "archive_only": True, "required_keys": ["exit_code", "binary_sha256", "binary_custody"],
            "binary_custody_required_keys": ["raw_sha256", "canonical_sha256", "format", "machine", "profile", "normalization"],
            "environment_policy": {"rustc_wrapper_cleared": True, "rustc_workspace_wrapper_cleared": True, "cargo_build_rustc_wrapper_cleared": True},
        },
        "case_policy": _policies(), "claims": _claims(),
        "formal_evidence": {"manifest_present": False, "reports_present": False, "aggregate_present": False},
    }


def verify_prep(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    _check(blockers, document.get("schema") == "sipi.pb-02-metallic-python-oracle-prep.v2", "schema drift")
    _check(blockers, document.get("status") == "prep_only_no_formal_replay", "status drift")
    _check(blockers, document.get("candidate") == EXPECTED_CANDIDATE, "candidate identity drift")
    _check(blockers, document.get("upstream") == EXPECTED_UPSTREAM, "upstream identity drift")
    _check(blockers, document.get("source_mode") == EXPECTED_SOURCE_MODE, "source mode drift")
    corpus = document.get("corpus") if isinstance(document.get("corpus"), dict) else {}
    corpus_path = corpus.get("path")
    _check(blockers, corpus_path == "docs/baselines/pb-02-metallic-python-oracle-corpus.v1.json" and _relative(corpus_path), "corpus path drift")
    _check(blockers, corpus.get("case_ids") == EXPECTED_CASES and corpus.get("expected_fields") == EXPECTED_FIELDS, "corpus field list drift")
    try:
        _check(blockers, digest(root / corpus_path) == corpus.get("sha256"), "corpus hash drift")
        payload = json.loads((root / corpus_path).read_text(encoding="utf-8"))
        fixture = payload["base_fixture"]
        _check(blockers, _relative(fixture) and fixture == corpus.get("base_fixture"), "fixture binding drift")
        _check(blockers, digest(root / fixture) == corpus.get("base_fixture_sha256"), "fixture hash drift")
        _check(blockers, payload == {
            "schema": "sipi.pb-02-metallic-python-oracle-corpus.v1",
            "version": 1,
            "base_fixture": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml",
            "base_fixture_sha256": "2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f",
            "files": {},
            "cases": payload["cases"],
        }, "corpus schema drift")
        _check(blockers, [case.get("id") for case in payload["cases"]] == EXPECTED_CASES, "case id drift")
        expected_overrides = {
            EXPECTED_CASES[0]: {"l_ch": 0.05, "f_step": 3000.0, "f_max": 10.0, "impulse_length": 1.0, "ctle_enable": True, "random_noise_seed": 99},
            EXPECTED_CASES[1]: {"l_ch": 0.05, "f_step": 3000.0, "f_max": 3.0000000000000004, "impulse_length": 1.0, "ctle_enable": True, "random_noise_seed": 99},
        }
        _check(blockers, payload.get("files") == {}, "corpus files drift")
        for case in payload["cases"]:
            _check(blockers, case.get("expected_fields") == EXPECTED_FIELDS, f"field list drift: {case.get('id')}")
            _check(blockers, case.get("policy") == _policies()[case["id"]], f"case policy drift: {case.get('id')}")
            _check(blockers, case.get("overrides") == expected_overrides.get(case.get("id")), f"case override drift: {case.get('id')}")
    except (KeyError, OSError, json.JSONDecodeError):
        blockers.append("corpus or fixture missing")
    harness = document.get("harness") if isinstance(document.get("harness"), dict) else {}
    _check(blockers, set(harness) == set(HARNESS_PATHS), "harness key set drift")
    for path in HARNESS_PATHS:
        item = harness.get(path) if isinstance(harness.get(path), dict) else {}
        _check(blockers, item.get("path") == path and _relative(item.get("path")), f"harness path drift: {path}")
        try:
            _check(blockers, digest(root / path) == item.get("sha256") and HEX64.fullmatch(str(item.get("sha256"))) is not None, f"harness hash drift: {path}")
        except OSError:
            blockers.append(f"harness missing: {path}")
    toolchain = document.get("toolchain_contract") if isinstance(document.get("toolchain_contract"), dict) else {}
    _check(blockers, toolchain.get("required_roles") == ["cargo", "rustc", "uv", "python"] and toolchain.get("path_redacted") is True, "toolchain contract drift")
    _check(blockers, toolchain.get("required_keys") == ["role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"], "toolchain key set drift")
    _check(blockers, toolchain.get("child_python_required_keys") == ["command", "process", "identity"] and toolchain.get("child_python_identity_keys") == ["python", "numpy", "scipy"], "child Python key set drift")
    _check(blockers, toolchain.get("child_python_executable_keys") == ["executable", "file_sha256", "implementation", "version", "path_redacted"], "child Python executable key set drift")
    _check(blockers, toolchain.get("host_python_required_keys") == ["executable", "file_sha256", "path_redacted", "source"], "host Python key set drift")
    _check(blockers, toolchain.get("version_exit_code") == 0, "toolchain version gate drift")
    build = document.get("build_contract") if isinstance(document.get("build_contract"), dict) else {}
    _check(blockers, build.get("archive_only") is True, "build source mode drift")
    _check(blockers, build.get("required_keys") == ["exit_code", "binary_sha256", "binary_custody"], "build keys drift")
    _check(blockers, build.get("binary_custody_required_keys") == ["raw_sha256", "canonical_sha256", "format", "machine", "profile", "normalization"], "binary custody key set drift")
    _check(blockers, build.get("environment_policy") == {"rustc_wrapper_cleared": True, "rustc_workspace_wrapper_cleared": True, "cargo_build_rustc_wrapper_cleared": True}, "build wrapper environment policy drift")
    _check(blockers, document.get("case_policy") == _policies(), "case policy contract drift")
    _check(blockers, document.get("claims") == _claims(), "claims drift")
    _check(blockers, document.get("formal_evidence") == {"manifest_present": False, "reports_present": False, "aggregate_present": False}, "formal evidence overclaim")
    _check(blockers, PATH_LEAK.search(json.dumps(document, ensure_ascii=True)) is None, "absolute path leak")
    return {"valid": not blockers, "blockers": blockers}


def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    return verify_prep(document, root)


def main() -> int:
    result = verify_prep(prep_document())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
