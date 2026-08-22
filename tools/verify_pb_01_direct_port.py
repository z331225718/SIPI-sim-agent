"""Verify the PB-01 direct-port workflow-boundary candidate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "pb-01-direct-port.v1.yaml"
EXPECTED_SCHEMA = "sipi.pb-01-direct-port.v1"
EXPECTED_STATUS = "superseded_by_executable_scoped_leaf"
EXPECTED_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
EXPECTED_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
EXPECTED_CLI_BLOB = "4c1116007d31bcebf8db3252363eed7774c7b349"
EXPECTED_CLI_SHA = "3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9"
EXPECTED_MODULE = ("crates/sipi-pybert-direct/src/legacy_sim.rs", "c190daba96a71ebb9b8d60af1c3deb56e76b812a95d73d9c6fa3219ecb7e9eba")
EXPECTED_RUNNER = ("tools/run_pb_01_direct_replay.py", "eb82e484a55ad179ea11e03c8fc7e023cacfc13c7f0cc66494ea878527529b68")
EXPECTED_AGGREGATOR = ("tools/aggregate_pb_01_direct_replay.py", "47f3666ae72a2cadbe8a8dcef0665e4b55ac8738b3ffbb27d8e397cbdbd9855f")
EXPECTED_AUDIT = ("docs/baselines/audits/2026-08-23-pb-01-direct-port.md", "9ccf235ee5949c057f2ec5974296b4ef56f2d638608e38e4af74c30e4c899299")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PATH_LEAK_RE = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def _get(document: dict[str, Any], *keys: str) -> Any:
    value: Any = document
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _check_file_binding(root: Path, value: Any, expected: tuple[str, str], blockers: list[str], label: str) -> None:
    _check(blockers, isinstance(value, str) and value == expected[0], f"{label} path drift")
    if isinstance(value, str) and value == expected[0]:
        _check(blockers, _sha256_file(root / value) == expected[1], f"{label} hash drift")


def _verify_branch_inventory(document: dict[str, Any], blockers: list[str]) -> None:
    expected = {
        "invocation": {
            "command": "sim",
            "positional": ["CONFIG_FILE"],
            "optional": ["--results", "RESULTS_FILE"],
            "config_click_type": "click.Path(exists=true)",
            "results_click_type": "click.Path()",
        },
        "input_projection": {
            "config_loader": "PyBertCfg.load_from_file",
            "accepted_extensions": [".yaml", ".yml", ".pybert_cfg"],
            "yaml_loader": "safe_loader_with_PyBertCfg_and_tuple_constructors",
            "pickle_loader": "legacy_pybert_cfg_only",
            "unknown_extension": "InvalidFileType",
            "native_projection": "not_present",
        },
        "execution": {
            "backend": "PythonSimulationBackend",
            "validate": "called_with_pybert_instance",
            "simulate": "PyBERT.simulate",
            "initial_run": True,
            "update_plots": True,
            "aborted_callback": "always_false",
            "stage_callback": "no_op",
        },
        "backend_selection": {
            "requested_backend": "python",
            "selector": "none",
            "fallback": "forbidden",
            "auto_or_compare_branch": "not_reachable_from_sim",
        },
        "artifacts": {
            "default_result_path": "CONFIG_FILE.with_suffix(.pybert_data)",
            "explicit_result_path": "RESULTS_FILE_forwarded_unchanged",
            "codec": "PyBertData_pickle",
            "required_result_object": "PyBertData",
            "payload_decode_in_candidate": "forbidden",
            "save_errors": "upstream_save_results_logs_and_does_not_raise",
        },
        "error_surface": {
            "missing_config": "click_path_exists_error",
            "invalid_config_extension": "InvalidFileType",
            "malformed_or_wrong_type_config": "PyBertCfg_load_error",
            "simulation_backend_error": "propagated_from_PythonSimulationBackend",
            "result_write_error": "logged_by_PyBert.save_results_artifact_postcondition_must_still_fail",
        },
    }
    actual = document.get("branch_inventory")
    _check(blockers, isinstance(actual, dict), "branch inventory missing")
    if not isinstance(actual, dict):
        return
    for key, expected_value in expected.items():
        _check(blockers, actual.get(key) == expected_value, f"branch inventory drift: {key}")


def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    _check(blockers, document.get("schema") == EXPECTED_SCHEMA, "schema drift")
    _check(blockers, document.get("status") == EXPECTED_STATUS, "status drift")
    scope = document.get("scope")
    _check(blockers, isinstance(scope, dict), "scope missing")
    if isinstance(scope, dict):
        for key, value in {
            "workflow": "PB-01",
            "command": "sim",
            "lane_crate": "crates/sipi-pybert-direct",
            "candidate_module": EXPECTED_MODULE[0],
            "product_workspace_modified": False,
            "adapter_semantics_modified": False,
            "new_domain_feature": False,
            "numerical_replacement": "not_started",
        }.items():
            _check(blockers, scope.get(key) == value, f"scope.{key} drift")
    source = document.get("source")
    _check(blockers, isinstance(source, dict), "source missing")
    if isinstance(source, dict):
        for key, value in {
            "repository": "pybert",
            "commit": EXPECTED_COMMIT,
            "tree": EXPECTED_TREE,
            "cli_path": "src/pybert/cli.py",
            "cli_blob_oid_sha1": EXPECTED_CLI_BLOB,
            "cli_content_sha256": EXPECTED_CLI_SHA,
            "license": "BSD-3-Clause",
            "source_bytes_policy": "exact_git_objects_only",
            "source_bytes_in_repository": False,
        }.items():
            _check(blockers, source.get(key) == value, f"source.{key} drift")
        expected_objects = {
            "src/pybert/cli.py": EXPECTED_CLI_BLOB,
            "src/pybert/configuration.py": "ef24ded89768291e7b5e945fab4fe50be3bd6c2d",
            "src/pybert/pybert.py": "1af665c4595fff1ff5fb30341fe063bd10e5cd89",
            "src/pybert/results.py": "4d8eafa77a20ef8a3ac307f6ae8c0397deb8e907",
            "src/pybert/engine/python_backend.py": "6b7b664d89da1502c74fc7cd97fe4451bf98ab82",
        }
        _check(blockers, source.get("source_objects") == expected_objects, "source object inventory drift")
    _check(
        blockers,
        document.get("relationship")
        == {
            "record_role": "predecessor_boundary_inventory",
            "superseded_by": "docs/baselines/pb-01-legacy-leaf.v1.yaml",
            "supersession_scope": "active_implementation_status_for_scoped_nrz_metallic_line_leaf",
            "retained_scope": "full_pb01_branch_default_error_artifact_inventory",
            "executable_leaf_branch_complete": False,
        },
        "supersession relationship drift",
    )
    _verify_branch_inventory(document, blockers)
    candidate = document.get("candidate")
    _check(blockers, isinstance(candidate, dict), "candidate missing")
    if isinstance(candidate, dict):
        for key, value in {
            "source_mode": "working_tree_candidate_not_immutable",
            "status": "boundary_contract_only_legacy_projection_blocked",
            "module_sha256": EXPECTED_MODULE[1],
            "request_type": "LegacySimRequestV1",
            "default_resolution": "LegacySimRequestV1.resolved_results_path",
            "native_core_reuse": "sipi_pybert_direct::run_sim_native_file_reserved_for_proven_projection",
            "does_not_parse_legacy_yaml_or_pickle": True,
            "does_not_run_PyBERT_numeric_graph": True,
            "does_not_fallback_to_native_input_guess": True,
        }.items():
            _check(blockers, candidate.get(key) == value, f"candidate.{key} drift")
        _check_file_binding(root, scope.get("candidate_module") if isinstance(scope, dict) else None, EXPECTED_MODULE, blockers, "candidate module")
    oracle = document.get("oracle_runner")
    _check(blockers, isinstance(oracle, dict), "oracle runner missing")
    if isinstance(oracle, dict):
        for key, value in {
            "prepare_path": EXPECTED_RUNNER[0],
            "aggregate_path": EXPECTED_AGGREGATOR[0],
            "prepare_sha256": EXPECTED_RUNNER[1],
            "aggregate_sha256": EXPECTED_AGGREGATOR[1],
            "mode": "two_stage_source_preparation_then_optional_external_replay",
            "reports_bound": False,
        }.items():
            _check(blockers, oracle.get(key) == value, f"oracle runner.{key} drift")
        _check_file_binding(root, oracle.get("prepare_path"), EXPECTED_RUNNER, blockers, "oracle runner")
        _check_file_binding(root, oracle.get("aggregate_path"), EXPECTED_AGGREGATOR, blockers, "oracle aggregate")
        _check(blockers, oracle.get("report_statuses") == ["prepared_open", "observed_open"], "oracle status set drift")
        _check(blockers, oracle.get("stage_1") == "immutable_candidate_and_upstream_archive_identity_plus_opaque_config_hash", "oracle stage 1 drift")
        _check(blockers, oracle.get("stage_2") == "optional_pinned_external_pybert_sim_and_caller_supplied_candidate_process", "oracle stage 2 drift")
    parity = document.get("parity")
    _check(blockers, parity == {"status": "not_evaluated", "numeric_payload_compared": False, "branch_complete": False, "row_promotion": "forbidden"}, "parity boundary drift")
    claims = document.get("claims")
    _check(blockers, isinstance(claims, dict), "claims missing")
    if isinstance(claims, dict):
        _check(blockers, all(value is False for value in claims.values()), "claim boundary drift")
    audit = document.get("audit")
    _check(blockers, isinstance(audit, dict), "audit missing")
    if isinstance(audit, dict):
        _check(blockers, audit.get("path") == EXPECTED_AUDIT[0], "audit path drift")
        _check(blockers, audit.get("sha256") == EXPECTED_AUDIT[1], "audit hash binding drift")
        _check(blockers, _sha256_file(root / EXPECTED_AUDIT[0]) == EXPECTED_AUDIT[1], "audit content hash drift")
    serialized = json.dumps(document, ensure_ascii=True, sort_keys=True, default=str)
    _check(blockers, PATH_LEAK_RE.search(serialized) is None, "evidence contains an absolute host path")
    expected_non_claims = {
        "This candidate does not copy PyBERT Python source, fixtures, arrays, pickle payloads, DLLs, or runtime assets.",
        "The predecessor boundary module itself does not implement a YAML/PyBertCfg parser, PyBertData codec, or legacy numeric simulation; the scoped executable leaf is recorded separately.",
        "The existing native core is reusable infrastructure only; it is not a PB-01 projection or parity result.",
        "The oracle runner does not decode or compare legacy pickle numeric payloads.",
        "SIPI wrapper behavior is not upstream PyBERT parity.",
        "This record is not a license conclusion, product admission, release approval, or redistribution authorization.",
    }
    non_claims = document.get("non_claims")
    _check(blockers, isinstance(non_claims, list) and expected_non_claims.issubset(non_claims), "non-claim boundary drift")
    return {"valid": not blockers, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.evidence.read_text(encoding="utf-8"))
        result = verify(document)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
