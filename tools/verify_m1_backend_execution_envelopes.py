"""Semantic validation for the M1-02A strict adapter SPI draft."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver

from verify_m1_run_envelopes import validate_request
from verify_m1_runtime_validation import validate_platform_error, validate_resource_usage
from verify_m1_artifacts import validate_artifact_collection, validate_artifact_ref


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
REQUEST_SCHEMA = json.loads((ROOT / "schemas/backend-execution-request.v1.schema.json").read_text())
RESULT_SCHEMA = json.loads((ROOT / "schemas/backend-execution-result.v1.schema.json").read_text())
REQUEST_RESOLVER = RefResolver(base_uri=(ROOT / "schemas/").as_uri() + "/", referrer=REQUEST_SCHEMA)
RESULT_RESOLVER = RefResolver(base_uri=(ROOT / "schemas/").as_uri() + "/", referrer=RESULT_SCHEMA)
REQUEST_FIELDS = {
    "schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role",
    "engine_instance_id", "bundle_hash", "operation", "payload_schema", "payload",
    "payload_artifact", "bound_inputs", "resource_limits", "artifact_policy", "randomness",
    "selection_hash",
}
RESULT_FIELDS = {
    "schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role",
    "engine_instance_id", "bundle_hash", "operation", "payload_schema", "status",
    "domain_result_schema", "domain_result", "artifacts", "events", "warnings", "timings",
    "resource_usage", "error",
}
FORBIDDEN_RESULT_FIELDS = {"backend_selection", "fallback_trace", "comparison"}


def _same_payload_transport(run_request, backend_request):
    for field in ("payload", "payload_artifact"):
        if (field in run_request) != (field in backend_request):
            raise ValueError("payload transport mismatch")
        if field in run_request and backend_request[field] != run_request[field]:
            raise ValueError("payload mismatch")


def validate_backend_request(run_request, backend_request, expected_selection_hash, allow_internal=False):
    """Ensure runtime made the only selection before invoking a strict adapter."""
    Draft202012Validator(REQUEST_SCHEMA, resolver=REQUEST_RESOLVER).validate(backend_request)
    validate_request(run_request, allow_internal=allow_internal)
    for field in ("run_id", "analysis_id", "attempt_id", "operation", "payload_schema"):
        if backend_request[field] != run_request[field]:
            raise ValueError(f"{field} mismatch")
    _same_payload_transport(run_request, backend_request)
    if "payload_artifact" in backend_request: validate_artifact_ref(backend_request["payload_artifact"])
    validate_artifact_collection(list(backend_request["bound_inputs"].values()))
    if backend_request["selection_hash"] != expected_selection_hash:
        raise ValueError("selection_hash mismatch")

    selection = run_request["backend_selection"]
    mode = selection["mode"]
    if mode in {"strict", "auto"} and backend_request["role"] != "primary":
        raise ValueError("strict/auto adapter role must be primary")
    if mode == "strict" and backend_request["engine_instance_id"] != selection["instance"]:
        raise ValueError("strict instance mismatch")
    if mode == "auto" and backend_request["engine_instance_id"] not in selection["candidates"]:
        raise ValueError("auto instance is not a resolved candidate")
    if mode == "compare":
        if backend_request["role"] not in {"reference", "candidate"}:
            raise ValueError("compare adapter role must be reference or candidate")
        expected = selection[backend_request["role"]]
        if backend_request["engine_instance_id"] != expected:
            raise ValueError("compare role/instance mismatch")


def validate_backend_result(backend_request, result, producer=True):
    """Ensure one adapter result exactly echoes one strict backend request."""
    Draft202012Validator(RESULT_SCHEMA, resolver=RESULT_RESOLVER).validate(result)
    if FORBIDDEN_RESULT_FIELDS & set(result):
        raise ValueError("adapter result contains runtime orchestration fields")
    for field in ("run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema"):
        if result[field] != backend_request[field]:
            raise ValueError(f"{field} mismatch")
    if result["status"] == "succeeded":
        if not isinstance(result["domain_result_schema"], str) or not result["domain_result_schema"]:
            raise ValueError("successful result requires a domain result schema")
        if result["error"] is not None:
            raise ValueError("successful result cannot contain an error")
        if "domain_result" not in result and not result["artifacts"]:
            raise ValueError("successful result requires an inline result or artifact")
    elif not isinstance(result["error"], dict):
        raise ValueError("failed/cancelled result requires an error object")
    if result["error"] is not None:
        validate_platform_error(result["error"], producer=producer)
        if result["status"] == "cancelled" and result["error"]["category"] != "Cancelled": raise ValueError("cancelled result requires Cancelled")
        if result["status"] == "failed" and result["error"]["category"] == "Cancelled": raise ValueError("failed result cannot use Cancelled")
    validate_resource_usage(backend_request["resource_limits"], result["resource_usage"])
    validate_artifact_collection(result["artifacts"], producer=producer)
    if "domain_result" in result and (not isinstance(result["domain_result_schema"], str) or not result["domain_result_schema"]):
        raise ValueError("inline domain result requires a domain result schema")
    if producer:
        unknown = set(result) - RESULT_FIELDS
        if unknown:
            raise ValueError(f"adapter result has unnamespaced fields: {sorted(unknown)}")


from jsonschema import ValidationError
from sipi_contracts.errors import ContractViolation
from sipi_contracts.validation.relations import validate_backend_request as _validate_backend_request, validate_backend_result as _validate_backend_result


def _compat(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except ContractViolation as error:
        if error.code == "schema":
            raise ValidationError(error.message) from error
        raise


def validate_backend_request(run_request, backend_request, expected_selection_hash, allow_internal=False):
    return _compat(_validate_backend_request, run_request, backend_request, expected_selection_hash, allow_internal=allow_internal)


def validate_backend_result(backend_request, result, producer=True):
    return _compat(_validate_backend_result, backend_request, result, producer=producer)
