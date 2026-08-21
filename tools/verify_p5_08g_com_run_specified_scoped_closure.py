"""Verify the additive P5-08g specified/non-oracle COM child closure."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs/baselines/p5-08g-com-run-specified-scoped-closure.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p5-08g-com-run-specified-scoped-closure.md"
SCHEMA = "sipi.p5-08g.com-run-specified-scoped-closure.v1"
POLICY = "sipi.p5-08g.com-run-artifact-specified-non-oracle-scoped-closure-v1"

IMPLEMENTATION = {
    "parameter_module": (
        "crates/sipi-com/src/com_specified_parameter_ingestion_v1.rs",
        "9f5ed916d2566b66e2b3401ecd3fe8973020fce9755cf71496f3069c5d0b28b6",
    ),
    "execution_module": (
        "crates/sipi-com/src/com_specified_artifact_execution_v1.rs",
        "b25be2b0450137ccd8a5cdf15640c5b8f0dff68aed19fb36452944198017633f",
    ),
    "public_surface": (
        "crates/sipi-com/src/lib.rs",
        "64f6e08a176f3f30f1d1144ffe30c97f78b6ca2a08cb8b5151fb69468b422368",
    ),
    "cli_surface": (
        "crates/sipi-cli/src/main.rs",
        "f9e41429321731659ea458de1bd4550fe0a195e6bc8ba0d3ff910980b36d26b0",
    ),
    "preflight_module": (
        "crates/sipi-cli/src/com_run_artifact_preflight_v1.rs",
        "c39cf4b7a4cfc015226a25a7e368860bf3fa33af23c7c1c3394f679815034525",
    ),
    "contract_source": (
        "crates/sipi-contracts/src/lib.rs",
        "6bc98037d55bc76a93edeca8b5930d29daf84893a6c86e1134c72b07eb758d12",
    ),
    "contract_schema": (
        "crates/sipi-contracts/schemas/sipi.com.run-artifact-request.v1.schema.json",
        "1cdfb38d304128826e06b30ef3b43eb88c59b06a27f4ff26684b3b2210d6d5b0",
    ),
    "artifact_custody_source": (
        "crates/sipi-artifacts/src/lib.rs",
        "53e8636b2f61bb1d58e043de8bcc505830f84077b95b0d4333cd57965cab9669",
    ),
}

HISTORY = {
    "p5-08e": (
        "docs/baselines/p5-08e-com-run-artifact-execution.v1.yaml",
        "baeb4de8cf0698505ce622eaee2fbea1a0051bcff8e6ab889f6e129a6a4a9379",
    ),
    "p5-08f": (
        "docs/baselines/p5-08f-specified-com-artifact-route.v1.yaml",
        "8d7fa496b43e3c4c6ef685be1f36113d0307c3cdb91f0d2dac7dd9e3c73ccded",
    ),
}

EXPECTED_NON_CLAIMS = [
    "not_agent_com_parity",
    "not_external_provenance",
    "not_external_ownership",
    "not_external_signature",
    "not_hostile_writer_safe",
    "not_authoritative_profile_or_oracle",
    "not_acceptance",
    "not_ieee_certification",
    "not_release_evidence",
    "not_p5_02_or_p5_06_changed",
]


class P508gError(RuntimeError):
    """Raised when the scoped closure record or live route drifts."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise P508gError(reason)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise P508gError(f"load_failed:{path}") from error
    _require(isinstance(value, dict), f"document_not_mapping:{path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise P508gError(f"read_failed:{path}") from error


def _source(root: Path, relative: str) -> str:
    path = root / relative
    _require(path.is_file(), f"source_missing:{relative}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise P508gError(f"source_read_failed:{relative}") from error


def _validate_source_bindings(root: Path, implementation: dict[str, Any]) -> None:
    _require(set(implementation) == set(IMPLEMENTATION) | {
        "route",
        "request_schema",
        "response_schema",
        "library_entrypoint",
        "cli_entrypoint",
    }, "implementation_shape_invalid")
    for key, (relative, digest) in IMPLEMENTATION.items():
        binding = implementation.get(key)
        _require(
            binding == {"path": relative, "sha256": digest},
            f"implementation_binding_invalid:{key}",
        )
        _require(_sha256(root / relative) == digest, f"source_hash_drift:{key}")


def _validate_live_sources(root: Path) -> None:
    parameter = _source(root, IMPLEMENTATION["parameter_module"][0])
    for marker in (
        "COM_SPECIFIED_PARAMETER_INGESTION_POLICY_V1",
        "ValueOutsideConsumed",
        "ProvidedAndDefaultOverlap",
        "DuplicateUnconsumed",
        "merge_com_parameters_v1",
        "reports_provided_defaulted_and_unconsumed_without_workbook_claim",
        "rejects_values_outside_partition",
        "rejects_provided_default_overlap",
    ):
        _require(marker in parameter, f"parameter_marker_missing:{marker}")

    execution = _source(root, IMPLEMENTATION["execution_module"][0])
    for marker in (
        "pub fn execute_com_run_artifact_from_product_values_v1",
        "ingest_com_specified_parameters_v1",
        "consume_exact_verified_v1",
        "[(COM_RUN_PULSE_FILE_V1, COM_RUN_PULSE_MAX_BYTES_V1)]",
        "VerifiedConsumptionPolicyV1::try_new",
        "COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1",
        "COM_RUN_RESULT_MAX_BYTES_V1",
        "stage_reader(",
        "publish_new()",
        "COM_RUN_ARTIFACT_SPECIFIED_RESULT_SCHEMA_V1",
        '"workbook_value_keys": []',
        '"agent_com_parity": "not_claimed"',
        '"external_acceptance": "blocked"',
        '"ieee_certification": false',
        '"release_evidence": false',
    ):
        _require(marker in execution, f"execution_marker_missing:{marker}")
    result_projection = execution[execution.index("fn result_payload") :]
    for forbidden in ("artifact_root", "pulse_root", "waveform"):
        _require(forbidden not in result_projection.lower(), f"result_leakage_marker:{forbidden}")
    for required in ("pulse_sample_count", "manifest_sha256", "invalid_reason"):
        _require(required in result_projection, f"result_projection_missing:{required}")

    public = _source(root, IMPLEMENTATION["public_surface"][0])
    _require(
        "mod com_specified_parameter_ingestion_v1;" in public
        and "mod com_specified_artifact_execution_v1;" in public
        and "execute_com_run_artifact_from_product_values_v1" in public,
        "public_surface_missing",
    )

    contract = _source(root, IMPLEMENTATION["contract_source"][0])
    for marker in (
        "#[serde(deny_unknown_fields)]",
        "pub struct ComRunArtifactRequestV1",
        "pub fn parse_com_run_artifact_request_v1",
        "request.consumed_keys.len() > 64",
        "!unique_strings(&request.consumed_keys)",
        "valid_com_parameter_value",
        "value.is_finite()",
    ):
        _require(marker in contract, f"contract_marker_missing:{marker}")

    artifact = _source(root, IMPLEMENTATION["artifact_custody_source"][0])
    for marker in (
        "pub fn consume_exact_verified_v1",
        "rechecked",
        "list_regular_files",
        "require_regular_file",
        "The root is not a hostile-writer boundary",
    ):
        _require(marker in artifact, f"custody_marker_missing:{marker}")

    cli = _source(root, IMPLEMENTATION["cli_surface"][0])
    for marker in (
        'id: "com.run-artifact"',
        'route: &["com", "run-artifact"]',
        "availability: CommandAvailabilityV1::Available",
        'request_schema: Some(COM_RUN_ARTIFACT_REQUEST_SCHEMA)',
        'response_schema: Some("sipi.com.run-artifact-specified-result.v1")',
        'nonclaim: "product_owned_bounded_artifact_execution_non_oracle_only"',
        'command_id: "com.run-artifact"',
        'required_options: &["--pulse-root"]',
        'validation_rule_id: Some("com.run-artifact.specified-non-oracle.v1")',
        'action == "run-artifact"',
        "fn com_run_artifact_stdin",
        "COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1",
        'id: "com.run"',
        'availability: CommandAvailabilityV1::Unavailable',
        'unavailable_reason: Some("com_profile_not_admitted")',
        "specified_com_artifact_route_is_explicit_and_legacy_com_stays_closed",
        "specified_com_request_result_and_cli_route_share_one_bounded_schema",
        "read_bounded_stdin_request(COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1)",
        "preflight_com_run_artifact_request_v1(&input)",
    ):
        _require(marker in cli, f"cli_marker_missing:{marker}")
    route_segment = cli[cli.index("fn com_run_artifact_stdin") : cli.index("fn read_stdin_request")]
    _require(
        route_segment.index("read_bounded_stdin_request")
        < route_segment.index("preflight_com_run_artifact_request_v1")
        < route_segment.index("parse_com_run_artifact_request_v1"),
        "preflight_order_invalid",
    )
    reader_segment = cli[cli.index("fn read_bounded_stdin_request") : cli.index("fn run_com_artifact")]
    for marker in ("take((maximum + 1) as u64)", "input.len() > maximum"):
        _require(marker in reader_segment, f"bounded_reader_marker_missing:{marker}")
    run_segment = cli[cli.index("fn run_com_artifact(") : cli.index("fn json_f64")]
    success_segment = run_segment[run_segment.index("success(format!(") :]
    for forbidden in ("pulse_root_path", "artifact_root", "waveform"):
        _require(forbidden not in success_segment.lower(), f"cli_result_leakage_marker:{forbidden}")

    preflight = _source(root, IMPLEMENTATION["preflight_module"][0])
    for marker in (
        "preflight_com_run_artifact_request_v1",
        "COM_RUN_ARTIFACT_PREFLIGHT_MAX_CONTAINERS_V1",
        "COM_RUN_ARTIFACT_PREFLIGHT_MAX_CONTAINER_ITEMS_V1",
        "COM_RUN_ARTIFACT_PREFLIGHT_MAX_STRING_BYTES_V1",
        "COM_RUN_ARTIFACT_PREFLIGHT_MAX_NESTING_V1",
        "RequestTooLarge",
        "ContainerBudgetExceeded",
        "StringBudgetExceeded",
    ):
        _require(marker in preflight, f"preflight_marker_missing:{marker}")


def _validate_schema(root: Path) -> None:
    path = root / IMPLEMENTATION["contract_schema"][0]
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise P508gError("request_schema_invalid") from error
    _require(schema.get("type") == "object", "request_schema_type_invalid")
    _require(schema.get("additionalProperties") is False, "request_schema_unknown_fields_open")
    required = {
        "schema",
        "request_id",
        "pulse_artifact_id",
        "pulse_manifest_sha256",
        "artifact_root",
        "artifact_id",
        "consumed_keys",
        "params",
        "defaults",
        "unconsumed_keys",
    }
    _require(set(schema.get("required", [])) == required, "request_schema_required_drift")
    properties = schema.get("properties")
    _require(isinstance(properties, dict) and set(properties) == required, "request_schema_properties_drift")
    for key in ("params", "defaults"):
        _require(
            properties[key].get("type") == "object"
            and properties[key].get("additionalProperties", {}).get("$ref")
            == "#/$defs/ComParameterValueV1",
            f"request_schema_parameter_map_invalid:{key}",
        )
    value_schema = schema.get("$defs", {}).get("ComParameterValueV1", {})
    _require(len(value_schema.get("anyOf", [])) == 5, "request_schema_value_categories_invalid")


def _validate_history(root: Path, bindings: Any) -> None:
    _require(isinstance(bindings, list), "history_bindings_invalid")
    expected = [
        {"id": key, "path": relative, "sha256": digest}
        for key, (relative, digest) in HISTORY.items()
    ]
    _require(bindings == expected, "history_bindings_drift")
    for relative, digest in HISTORY.values():
        _require(_sha256(root / relative) == digest, f"history_hash_drift:{relative}")


def validate(document: dict[str, Any] | None = None, root: Path = ROOT) -> dict[str, Any]:
    document = _load(CHARTER) if document is None else document
    _require(
        set(document)
        == {
            "schema",
            "status",
            "policy",
            "closure",
            "threat_model",
            "implementation",
            "contract",
            "scope",
            "bindings",
            "non_claims",
            "tests",
            "audit",
        },
        "charter_shape_invalid",
    )
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "scoped_specified_non_oracle_closed_p5_08_main_open", "status_invalid")
    _require(document.get("policy") == POLICY, "policy_invalid")
    _require(
        document.get("closure")
        == {
            "d6": "A",
            "route": ["com", "run-artifact"],
            "scope": "specified_non_oracle_exact_artifact_route",
            "closure_kind": "additive_child_closure",
            "p5_08_scoped_close": True,
            "p5_08_main_item_closed": False,
            "child_closure_required": True,
            "rationale": "full_p5_08_conformance_requires_external_profile_oracle_and_acceptance",
        },
        "closure_decision_invalid",
    )
    _require(
        document.get("threat_model")
        == {
            "writer_model": "non_hostile_concurrent_writer_only",
            "custody": "local_exact_verified_no_hostile_writer_guarantee",
            "hostile_writer_safe": False,
            "external_provenance": False,
            "external_ownership": False,
            "external_signature": False,
        },
        "threat_model_invalid",
    )
    implementation = document.get("implementation")
    _require(isinstance(implementation, dict), "implementation_missing")
    _validate_source_bindings(root, implementation)
    _require(implementation["route"] == ["com", "run-artifact"], "route_invalid")
    _require(implementation["request_schema"] == "sipi.com.run-artifact-request.v1", "request_schema_binding_invalid")
    _require(implementation["response_schema"] == "sipi.com.run-artifact-specified-result.v1", "response_schema_binding_invalid")
    _require(implementation["library_entrypoint"] == "execute_com_run_artifact_from_product_values_v1", "library_entrypoint_invalid")
    _require(implementation["cli_entrypoint"] == "com_run_artifact_stdin", "cli_entrypoint_invalid")
    _validate_live_sources(root)
    _validate_schema(root)
    _validate_history(root, document.get("bindings"))
    _require(
        document.get("contract")
        == {
            "caller_owned_parameter_partition": {
                "authority": "caller_supplied_explicit_consumed_provided_defaulted_unconsumed_sets",
                "unknown_fields": "rejected",
                "values_outside_consumed": "rejected",
                "provided_default_overlap": "rejected",
                "duplicate_unconsumed": "rejected",
                "workbook_values": "forbidden",
                "profile_inference": False,
                "auto_tuning": False,
            },
            "pulse": {
                "exact_file_set": ["pulse.f64le"],
                "encoding": "finite_little_endian_f64",
                "sealed_manifest_sha256_required": True,
                "maximum_manifest_bytes": 65536,
                "maximum_payload_bytes": 524288,
                "custody_call": "consume_exact_verified_v1",
            },
            "request": {
                "maximum_bytes": 65536,
                "maximum_containers": 256,
                "maximum_container_items": 256,
                "maximum_string_bytes": 4096,
                "maximum_nesting": 32,
                "budget_stage": "bounded_stdin_reader_and_lexical_preflight_before_deserialize_or_artifact_access",
            },
            "result": {
                "schema": "sipi.com.run-artifact-specified-result.v1",
                "exact_file": "result.json",
                "maximum_bytes": 16384,
                "publication": "immutable_publish_new",
                "output_binding": "caller_owned_root_and_id",
            },
            "leakage": {
                "path_leakage": False,
                "waveform_leakage": False,
                "payload_leakage": False,
                "result_allowlist": [
                    "artifact_id",
                    "manifest_sha256",
                    "payload_name",
                    "pulse_sample_count",
                    "parameter_key_sets",
                    "bounded_result_scalars",
                    "scope_flags",
                ],
            },
        },
        "contract_scope_invalid",
    )
    _require(
        document.get("scope")
        == {
            "product_owned_bounded_execution": True,
            "agent_com_parity": False,
            "external_provenance": False,
            "external_ownership": False,
            "external_signature": False,
            "hostile_writer_safe": False,
            "authoritative_profile": False,
            "authoritative_oracle": False,
            "external_acceptance": False,
            "ieee_certification": False,
            "release_evidence": False,
            "p5_02_unchanged": True,
            "p5_06_unchanged": True,
        },
        "scope_flags_invalid",
    )
    _require(document.get("non_claims") == EXPECTED_NON_CLAIMS, "non_claims_invalid")
    tests = document.get("tests")
    _require(
        tests
        == {
            "rust_surface": {
                "path": "crates/sipi-cli/src/main.rs",
                "sha256": IMPLEMENTATION["cli_surface"][1],
            },
            "required_cases": [
                "specified_com_artifact_route_is_explicit_and_legacy_com_stays_closed",
                "specified_com_request_result_and_cli_route_share_one_bounded_schema",
                "reports_provided_defaulted_and_unconsumed_without_workbook_claim",
                "rejects_values_outside_partition",
                "rejects_provided_default_overlap",
                "accepts_bounded_nested_request_shape",
                "rejects_oversized_request_before_deserialization",
                "rejects_long_string_and_container_budget",
            ],
        },
        "test_binding_invalid",
    )
    _require(
        document.get("audit")
        == {
            "path": "docs/baselines/audits/2026-08-21-p5-08g-com-run-specified-scoped-closure.md",
            "sha256": _sha256(AUDIT),
        },
        "audit_binding_invalid",
    )
    return {
        "schema": SCHEMA,
        "valid": True,
        "closure": "specified_non_oracle_exact_artifact_route",
        "p5_08_scoped_close": True,
        "p5_08_main_item_closed": False,
        "threat_model": "non_hostile_concurrent_writer_only",
    }


def main() -> int:
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError, P508gError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
