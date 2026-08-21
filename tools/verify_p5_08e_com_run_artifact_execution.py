"""Verify the P5-08e bounded pulse-to-COM-to-result artifact consumer."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs/baselines/p5-08e-com-run-artifact-execution.v1.yaml"
SOURCE = ROOT / "crates/sipi-com/src/com_run_artifact_execution_v1.rs"
LIB = ROOT / "crates/sipi-com/src/lib.rs"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p5-08e-com-run-artifact-execution.md"
LEGACY_ARTIFACT_SOURCE = ROOT / "crates/sipi-com/src/com_run_artifact_provenance_v1.rs"

SCHEMA = "sipi.p5-08e.com-run-artifact-execution.v1"
POLICY = "sipi.p5-08e.com-run-artifact-execution-v1.bounded"
SOURCE_REF = "crates/sipi-com/src/com_run_artifact_execution_v1.rs"
AUDIT_REF = "docs/baselines/audits/2026-08-21-p5-08e-com-run-artifact-execution.md"
LEGACY_ARTIFACT_SHA256 = "a58270e247a36f22ec768378d586f4b14ba4c6492a203fb1d8dfdecc352ef41a"
EXPECTED_BINDINGS = {
    "parameter_ingestion": (
        "docs/baselines/p5-05g-com-parameter-ingestion-stage.v1.yaml",
        "fd5ef026eac48c16dbacbe24919fd503a7a13b2593cf6d5e4dcceec5dc1072f2",
    ),
    "request_admission": (
        "docs/baselines/p5-08a-com-run-admission-stage.v1.yaml",
        "bb8b0af330ae014c23137c4cebee5a3976a8b6e8a421f0e20b08be3f8ea2c799",
    ),
    "com_execution": (
        "docs/baselines/p5-08b-com-run-execution-stage.v1.yaml",
        "d5fa3e67b85a31ccb5142d2f50124117c42fa6deced51b440acb1bbb1d3d8d14",
    ),
    "artifact_report": (
        "docs/baselines/p5-08d-com-run-artifact-provenance-bounded.v1.yaml",
        "b6d3b865289eb05589cc2ede971fe268af4947473f200719d0903881f4ee5398",
    ),
}
EXPECTED_NON_CLAIMS = [
    "not_hostile_writer_safe",
    "not_external_origin_or_ownership_proof",
    "not_authoritative_com_oracle",
    "not_behavioral_replication",
    "not_metric_tolerance_or_profile_acceptance",
    "not_ieee_certification",
    "not_public_com_run_cli_admission",
    "not_release_evidence",
]


class P508eError(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise P508eError(reason)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise P508eError(f"load_failed:{path}") from error
    _require(isinstance(value, dict), f"document_not_mapping:{path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise P508eError(f"read_failed:{path}") from error


def _validate_bindings(document: dict[str, Any]) -> None:
    bindings = document.get("bindings")
    _require(isinstance(bindings, list), "bindings_invalid")
    by_id = {
        item.get("id"): item
        for item in bindings
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    _require(len(by_id) == len(bindings), "binding_duplicate_or_invalid")
    _require(set(by_id) == set(EXPECTED_BINDINGS), "binding_set_invalid")
    for binding_id, (relative, digest) in EXPECTED_BINDINGS.items():
        _require(
            by_id[binding_id] == {"id": binding_id, "path": relative, "sha256": digest},
            f"binding_metadata_drift:{binding_id}",
        )
        path = ROOT / relative
        _require(path.is_file(), f"binding_missing:{binding_id}")
        _require(_sha256(path) == digest, f"binding_content_drift:{binding_id}")


def validate(root: Path = ROOT) -> dict[str, Any]:
    del root
    document = _load(CHARTER)
    _require(
        set(document)
        == {
            "schema",
            "status",
            "policy",
            "implementation",
            "bindings",
            "input",
            "output",
            "report",
            "non_claims",
            "audit",
        },
        "charter_shape_invalid",
    )
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(
        document.get("status")
        == "bounded_library_composition_implemented_external_acceptance_blocked",
        "status_invalid",
    )
    _require(document.get("policy") == POLICY, "policy_invalid")
    implementation = document.get("implementation")
    _require(isinstance(implementation, dict), "implementation_missing")
    _require(
        set(implementation) == {"path", "sha256", "function", "test_count"}
        and implementation.get("path") == SOURCE_REF
        and implementation.get("function") == "execute_com_run_artifact_v1"
        and implementation.get("test_count") == 7,
        "implementation_metadata_invalid",
    )
    _require(_sha256(SOURCE) == implementation.get("sha256"), "source_hash_drift")
    source = SOURCE.read_text(encoding="utf-8")
    for token in (
        "pub fn execute_com_run_artifact_v1",
        "consume_exact_verified_v1",
        "execute_com_run_v1",
        "inspect_com_run_artifact_provenance_v1",
        "parameters.dto()",
        "parameters.report()",
        "validate_request_parameter_projection",
        "RequestParameterMismatch",
        "RequestTooLarge",
        "COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1",
        "CAPABILITY_LABEL",
        "REPORT_CLAIM",
        "REPORT_DISCLAIMER",
        "CAPABILITY_DESCRIPTION",
        "CAPABILITY_DISCLAIMER",
        "EXTERNAL_ORACLE_STATEMENT",
        "METRICS_STATEMENT",
        "RUNTIME_STATEMENT",
        "COM_RUN_PULSE_FILE_V1",
        "publish_new",
        "product_owned_bounded_execution_complete",
        "blocked_missing_authoritative_reference",
    ):
        _require(token in source, f"source_binding_missing:{token}")
    library = LIB.read_text(encoding="utf-8")
    _require(
        "mod com_run_artifact_execution_v1;" in library
        and "execute_com_run_artifact_v1" in library,
        "library_export_missing",
    )
    _require(
        _sha256(LEGACY_ARTIFACT_SOURCE) == LEGACY_ARTIFACT_SHA256,
        "legacy_p5_08d_source_drift",
    )
    _validate_bindings(document)
    _require(
        document.get("input")
        == {
            "request_schema": "sipi.com.run-request.v1",
            "legacy_wire_changed": False,
            "identity_fields": ["artifact_id", "manifest_sha256"],
            "exact_payload_files": ["pulse.f64le"],
            "pulse_encoding": "finite_little_endian_f64",
            "maximum_manifest_bytes": 65536,
            "maximum_request_bytes": 65536,
            "maximum_pulse_bytes": 524288,
        },
        "input_contract_invalid",
    )
    _require(
        document.get("output")
        == {
            "result_payload_schema": "sipi.com.run-artifact-execution-result.v1",
            "result_file": "result.json",
            "maximum_result_bytes": 16384,
            "immutable_publish_new": True,
            "bounded_report_inspection": "p5-08d",
        },
        "output_contract_invalid",
    )
    report = document.get("report")
    _require(
        report
        == {
            "semantics": "product_owned_bounded_execution_complete",
            "behavioral_replication": "not_claimed",
            "external_acceptance": "blocked_missing_authoritative_reference",
            "product_acceptance": False,
            "promotion": False,
        },
        "report_scope_invalid",
    )
    _require(document.get("non_claims") == EXPECTED_NON_CLAIMS, "non_claims_invalid")
    audit = document.get("audit")
    _require(
        isinstance(audit, dict)
        and audit.get("path") == AUDIT_REF
        and audit.get("sha256") == _sha256(AUDIT),
        "audit_binding_invalid",
    )
    return {
        "schema": SCHEMA,
        "valid": True,
        "semantics": report["semantics"],
        "external_acceptance": report["external_acceptance"],
        "behavioral_replication": report["behavioral_replication"],
        "legacy_wire_changed": False,
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, P508eError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
