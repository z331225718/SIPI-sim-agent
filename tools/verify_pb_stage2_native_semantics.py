"""Verify the additive PB stage 2 native-semantics evidence boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "baselines" / "pb-stage2-native-semantics.v1.yaml"
EXPECTED_SCHEMA = "sipi.pb-stage2-native-semantics.v1"
EXPECTED_STATUS = "pending_immutable_external_replay"
EXPECTED_UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
EXPECTED_UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
EXPECTED_SOURCE_MAP = "crates/sipi-pybert-direct/SOURCE-MAP-PB-STAGE2.md"
EXPECTED_AUDIT = "docs/baselines/audits/2026-08-25-pb-stage2-native-semantics.md"
EXPECTED_AUDIT_SHA256 = "e3331a8c6a648eb97ff2febec41c787081e80065530e1d5fa7ad4a238a5f4d9b"
EXPECTED_SOURCE_MAP_SHA256 = "b990f276b13b02bc12f4d3e1744496468001b3a8a3eab8ece102a905bef6f265"
EXPECTED_FILES = {
    "crates/sipi-pybert-direct/src/simulation.rs": "50b22e87b74d8991dda3cbc81f3dd87dcd2c9cef18d476323d43c9b6020c0ba6",
    "crates/sipi-pybert-direct/src/workflows.rs": "a9a867d0df04d20afdeed8492dcc59ec16fd3ef3ce9e59a42556ac86791fef3e",
    "crates/sipi-pybert-direct/tests/native_branch_matrix.rs": "f05f949e992e13a524692fe411f1c80d3501590ac0ce704395eca811f3bb6a0e",
    "crates/sipi-pybert-direct/tests/workflows.rs": "75b83c9f9fa8fdd39b8a34ad99ad47b6864a7005d7cc1fec5d094a22e66b8f65",
    EXPECTED_SOURCE_MAP: EXPECTED_SOURCE_MAP_SHA256,
}
EXPECTED_BRANCHES = {
    "modulation.nrz": "native_branch_matrix::native_request_reaches_all_modulation_branches",
    "modulation.pam4": "native_branch_matrix::native_request_reaches_all_modulation_branches",
    "modulation.duo_binary": "native_branch_matrix::native_request_reaches_all_modulation_branches",
    "modulation.duo_binary.jitter_decision_scaler": "native_branch_matrix::native_duobinary_jitter_uses_typed_dfe_decision_scaler",
    "tx.rx.explicit_ffe_ctle_dfe_selection": "native_branch_matrix::native_request_reaches_impulse_tx_rx_ffe_dfe_ber_branches",
    "tx.rx.explicit_bypass": "native_branch_matrix::native_request_reaches_explicit_bits_and_disabled_equalizers",
    "output.schema_capabilities_events_artifacts": "workflows::compare_gates_complete_output_capabilities_and_events",
    "output.numeric_arrays_and_metrics": "workflows::compare_checks_payload_and_rejects_waveform_mutation",
}
EXPECTED_BLOCKERS = {
    "two_fresh_complete_output_replay",
    "analytic_metallic_and_s2p_oracle_parity",
    "ami_ibis_dll_and_python_class_pickle",
}
EXPECTED_BLOCKER_STATUSES = {
    "two_fresh_complete_output_replay": "pending",
    "analytic_metallic_and_s2p_oracle_parity": "retained_external_or_fail_closed",
    "ami_ibis_dll_and_python_class_pickle": "retained_external_or_fail_closed",
}
EXPECTED_CLAIMS = {
    "native_engine_reused": True,
    "supported_modulation_and_explicit_stage_coverage": True,
    "complete_typed_output_gate": True,
    "two_fresh_external_payload_parity": False,
    "global_row_closed": False,
    "release_approval": False,
    "license_decision": False,
}
EXPECTED_NON_CLAIMS = [
    "two_fresh_external_payload_parity",
    "global_row_closed",
    "release_approval",
    "license_decision",
    "s2p_analytic_metallic_parity",
    "ami_ibis_dll_behavior",
    "pybert_data_class_pickle_compatibility",
]
EXPECTED_HARNESS = {
    "verifier": "tools/verify_pb_stage2_native_semantics.py",
    "mutation_tests": "tools/test_verify_pb_stage2_native_semantics.py",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _error(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def verify(document: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    _error(
        errors,
        set(document)
        == {
            "schema",
            "version",
            "row",
            "status",
            "purpose",
            "source",
            "scope",
            "branches",
            "external_blockers",
            "verification",
            "harness",
            "audit",
            "claims",
            "non_claims",
        },
        "top-level schema keys drift",
    )
    _error(errors, document.get("schema") == EXPECTED_SCHEMA, "schema mismatch")
    _error(errors, document.get("version") == 1, "version mismatch")
    _error(errors, document.get("row") == "PB-02/PB-03", "row drift")
    _error(errors, isinstance(document.get("purpose"), str) and bool(document["purpose"]), "purpose type drift")
    _error(errors, document.get("status") == EXPECTED_STATUS, "status must remain pending_immutable_external_replay")

    source = document.get("source")
    _error(errors, isinstance(source, dict), "source record missing")
    source = source if isinstance(source, dict) else {}
    _error(errors, source.get("upstream_commit") == EXPECTED_UPSTREAM_COMMIT, "upstream commit drift")
    _error(errors, source.get("upstream_tree") == EXPECTED_UPSTREAM_TREE, "upstream tree drift")
    _error(errors, source.get("candidate_basis") == "working_tree_content_addressed", "candidate basis drift")
    _error(errors, source.get("preparation_commit") is None, "unbound preparation commit must remain null")
    _error(errors, source.get("source_map") == EXPECTED_SOURCE_MAP, "source-map path drift")
    _error(errors, isinstance(source.get("source_files"), dict), "source_files type drift")

    source_files = source.get("source_files")
    _error(errors, isinstance(source_files, dict), "source file hashes missing")
    if isinstance(source_files, dict):
        _error(errors, set(source_files) == set(EXPECTED_FILES), "source file set drift")
        for relative, expected in EXPECTED_FILES.items():
            path = root / relative
            _error(errors, path.is_file(), f"source file missing: {relative}")
            if path.is_file():
                actual = _sha256(path)
                _error(errors, actual == expected, f"source hash mismatch: {relative}")
                _error(errors, source_files.get(relative) == expected, f"manifest hash mismatch: {relative}")
                _error(
                    errors,
                    isinstance(source_files.get(relative), str)
                    and len(source_files[relative]) == 64
                    and all(character in "0123456789abcdef" for character in source_files[relative]),
                    f"source hash type drift: {relative}",
                )

    scope = document.get("scope")
    _error(errors, isinstance(scope, dict), "scope record missing")
    scope = scope if isinstance(scope, dict) else {}
    _error(
        errors,
        set(scope)
        == {"input_contract", "engine", "output_contract", "comparison", "no_second_simulation_core"},
        "scope keys drift",
    )
    for name in ("input_contract", "engine", "output_contract", "comparison"):
        _error(errors, isinstance(scope.get(name), str) and bool(scope[name]), f"scope type drift: {name}")
    _error(errors, type(scope.get("no_second_simulation_core")) is bool, "scope boolean type drift")
    _error(errors, scope.get("no_second_simulation_core") is True, "second simulation core claim drift")

    branches = document.get("branches")
    _error(errors, isinstance(branches, list), "branch list missing")
    branch_ids = set()
    if isinstance(branches, list):
        for branch in branches:
            if not isinstance(branch, dict):
                errors.append("branch entry is not a mapping")
                continue
            branch_id = branch.get("id")
            branch_ids.add(branch_id)
            _error(
                errors,
                set(branch) == {"id", "status", "test"},
                f"branch tuple keys drift: {branch_id}",
            )
            _error(
                errors,
                branch_id in EXPECTED_BRANCHES,
                f"unknown branch tuple: {branch_id}",
            )
            _error(errors, branch.get("status") == "covered", f"branch not covered: {branch_id}")
            expected_test = EXPECTED_BRANCHES.get(branch_id)
            _error(
                errors,
                isinstance(branch.get("test"), str)
                and branch.get("test") == expected_test,
                f"branch test tuple drift: {branch_id}",
            )
    _error(errors, branch_ids == set(EXPECTED_BRANCHES), "branch set drift")

    blockers = document.get("external_blockers")
    _error(errors, isinstance(blockers, list), "external blockers missing")
    blocker_ids = set()
    if isinstance(blockers, list):
        for blocker in blockers:
            if not isinstance(blocker, dict):
                errors.append("external blocker is not a mapping")
                continue
            blocker_ids.add(blocker.get("id"))
            _error(
                errors,
                set(blocker) == {"id", "status", "reason"},
                f"external blocker tuple keys drift: {blocker.get('id')}",
            )
            _error(
                errors,
                EXPECTED_BLOCKER_STATUSES.get(blocker.get("id")) == blocker.get("status"),
                f"external blocker status drift: {blocker.get('id')}",
            )
            _error(errors, isinstance(blocker.get("reason"), str) and bool(blocker["reason"]), f"blocker reason missing: {blocker.get('id')}")
    _error(errors, blocker_ids == EXPECTED_BLOCKERS, "external blocker set drift")

    verification = document.get("verification")
    _error(errors, isinstance(verification, dict), "verification record missing")
    verification = verification if isinstance(verification, dict) else {}
    _error(errors, set(verification) == {"focused_commands", "external_compare", "verifier", "mutation_tests"}, "verification keys drift")
    _error(errors, isinstance(verification.get("focused_commands"), list), "focused command list missing")
    if isinstance(verification.get("focused_commands"), list):
        _error(errors, all(isinstance(command, str) and command for command in verification["focused_commands"]), "focused command types drift")
    _error(errors, verification.get("external_compare") == "not_run", "external compare must remain explicitly not run")
    _error(errors, verification.get("verifier") == EXPECTED_HARNESS["verifier"], "verifier path drift")
    _error(errors, verification.get("mutation_tests") == EXPECTED_HARNESS["mutation_tests"], "mutation test path drift")

    harness = document.get("harness")
    _error(errors, isinstance(harness, dict), "harness record missing")
    harness = harness if isinstance(harness, dict) else {}
    _error(errors, set(harness) == set(EXPECTED_HARNESS), "harness key set drift")
    for name, relative in EXPECTED_HARNESS.items():
        record = harness.get(name)
        _error(errors, isinstance(record, dict), f"harness record missing: {name}")
        record = record if isinstance(record, dict) else {}
        _error(errors, set(record) == {"path", "sha256"}, f"harness tuple keys drift: {name}")
        _error(errors, record.get("path") == relative, f"harness path drift: {name}")
        digest = record.get("sha256")
        _error(
            errors,
            isinstance(digest, str) and len(digest) == 64 and all(character in "0123456789abcdef" for character in digest),
            f"harness sha256 type drift: {name}",
        )
        path = root / relative
        _error(errors, path.is_file(), f"harness file missing: {relative}")
        if path.is_file():
            actual = _sha256(path)
            _error(errors, record.get("sha256") == actual, f"manifest harness hash mismatch: {name}")

    audit = document.get("audit")
    _error(errors, isinstance(audit, dict), "audit record missing")
    audit = audit if isinstance(audit, dict) else {}
    _error(errors, audit.get("path") == EXPECTED_AUDIT, "audit path drift")
    audit_path = root / EXPECTED_AUDIT
    _error(errors, audit_path.is_file(), "audit file missing")
    if audit_path.is_file():
        actual = _sha256(audit_path)
        _error(errors, actual == EXPECTED_AUDIT_SHA256, "audit content hash drift")
        _error(errors, audit.get("sha256") == actual, "manifest audit hash mismatch")

    claims = document.get("claims")
    _error(errors, isinstance(claims, dict), "claims record missing")
    claims = claims if isinstance(claims, dict) else {}
    _error(errors, set(claims) == set(EXPECTED_CLAIMS), "claims key set drift")
    for name, expected in EXPECTED_CLAIMS.items():
        _error(errors, type(claims.get(name)) is bool, f"claim type drift: {name}")
        _error(errors, claims.get(name) is expected, f"claim value drift: {name}")

    non_claims = document.get("non_claims")
    _error(errors, type(non_claims) is list, "non_claims must be a list")
    _error(errors, non_claims == EXPECTED_NON_CLAIMS, "non_claims drift")

    return {
        "valid": not errors,
        "errors": errors,
        "status": document.get("status"),
        "branch_count": len(branch_ids),
        "blocker_count": len(blocker_ids),
        "external_compare": verification.get("external_compare"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    document = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    result = verify(document, root=ROOT)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
