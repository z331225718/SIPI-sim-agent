"""Validate M1-02 run envelopes without defining deferred domain contracts."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver
from verify_m1_runtime_validation import validate_platform_error, validate_resource_usage
from verify_m1_artifacts import validate_artifact_collection, validate_artifact_ref, validate_provenance


ROOT = Path(__file__).resolve().parents[1]
REQUEST_SCHEMA = json.loads((ROOT / "schemas/run-request.v1.schema.json").read_text())
RESULT_SCHEMA = json.loads((ROOT / "schemas/run-result.v1.schema.json").read_text())
REQUEST_RESOLVER = RefResolver(
    base_uri=(ROOT / "schemas/").as_uri() + "/", referrer=REQUEST_SCHEMA
)
RESULT_RESOLVER = RefResolver(
    base_uri=(ROOT / "schemas/").as_uri() + "/", referrer=RESULT_SCHEMA
)
FALLBACK_REASONS = {"EngineUnavailable", "UnsupportedCapability"}
RESULT_FIELDS = {
    "schema", "run_id", "analysis_id", "attempt_id", "operation", "payload_schema",
    "status", "selection_requested", "backend_executions", "fallback_trace",
    "comparison", "metrics_summary", "artifacts", "events", "event_log_artifact",
    "provenance", "timings", "resource_usage", "error", "warnings", "extensions",
}
EXECUTION_FIELDS = {
    "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "status",
    "domain_result_schema", "artifacts", "error",
}
FALLBACK_FIELDS = {"instance", "reason"}


def _reject_unrecognized_fields(value, allowed, description):
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{description} has unnamespaced fields: {sorted(unknown)}")


def _require_namespaced_keys(value, description):
    invalid = [key for key in value if "." not in key]
    if invalid:
        raise ValueError(f"{description} has unnamespaced keys: {sorted(invalid)}")


def validate_request(value, allow_internal=False):
    """Validate a closed request; callers must authorize internal opt-in separately."""
    Draft202012Validator(REQUEST_SCHEMA, resolver=REQUEST_RESOLVER).validate(value)
    selection = value["backend_selection"]
    if selection["mode"] == "compare" and selection["reference"] == selection["candidate"]:
        raise ValueError("compare reference and candidate must differ")
    if selection["mode"] == "auto" and set(selection["fallback_on"]) != FALLBACK_REASONS:
        raise ValueError("auto fallback reasons must be exactly the platform allowlist")
    if selection.get("allow_internal", False) and not allow_internal:
        raise ValueError("allow_internal requires authorized internal policy")
    if "payload_artifact" in value: validate_artifact_ref(value["payload_artifact"], producer=True)


def validate_result(request, value, producer=True, allow_internal=False):
    """Validate result/request identity and selection semantics.

    ``producer=False`` applies the forward-compatible consumer contract. Producer
    mode additionally rejects fields that would flatten domain output at this layer.
    """
    Draft202012Validator(RESULT_SCHEMA, resolver=RESULT_RESOLVER).validate(value)
    validate_request(request, allow_internal=allow_internal)
    if "backend_execution_id" in value:
        raise ValueError("backend_execution_id belongs to backend_executions")
    for field in ("run_id", "analysis_id", "attempt_id", "operation", "payload_schema"):
        if value[field] != request[field]:
            raise ValueError(f"{field} mismatch")
    if value["selection_requested"] != request["backend_selection"]:
        raise ValueError("selection mismatch")

    executions = value["backend_executions"]
    execution_ids = [item["backend_execution_id"] for item in executions]
    if len(execution_ids) != len(set(execution_ids)):
        raise ValueError("duplicate backend execution id")
    if value["status"] == "succeeded" and not executions:
        raise ValueError("successful result requires an execution")
    if value["status"] == "succeeded" and any(item["status"] != "succeeded" for item in executions):
        raise ValueError("successful result has unsuccessful execution")
    _validate_terminal_error(value, producer)
    validate_resource_usage(request["resource_limits"], value["resource_usage"])
    validate_provenance(value["provenance"], producer=producer)
    all_artifacts = list(value["artifacts"])
    if "event_log_artifact" in value:
        all_artifacts.append(value["event_log_artifact"])
    for execution in executions:
        all_artifacts.extend(execution["artifacts"])
    validate_artifact_collection(all_artifacts, producer=producer, provenance=value["provenance"])
    for execution in executions: _validate_terminal_error(execution, producer)

    selection = request["backend_selection"]
    mode = selection["mode"]
    roles = [item["role"] for item in executions]
    if mode == "compare":
        if sorted(roles) != ["candidate", "reference"]:
            raise ValueError("compare roles")
        by_role = {item["role"]: item for item in executions}
        if by_role["reference"]["engine_instance_id"] != selection["reference"]:
            raise ValueError("compare reference instance mismatch")
        if by_role["candidate"]["engine_instance_id"] != selection["candidate"]:
            raise ValueError("compare candidate instance mismatch")
        comparison = value["comparison"]
        if not comparison or comparison.get("profile") != selection["comparison_profile"]:
            raise ValueError("compare result requires matching comparison evidence")
    elif any(role != "primary" for role in roles):
        raise ValueError("non-compare roles")
    elif mode == "strict":
        if len(executions) > 1:
            raise ValueError("strict has multiple executions")
        if executions and executions[0]["engine_instance_id"] != selection["instance"]:
            raise ValueError("strict instance mismatch")
    else:
        if len(executions) > 1:
            raise ValueError("auto has multiple executions")
        trace = value["fallback_trace"]
        traced = [item["instance"] for item in trace]
        candidates = selection["candidates"]
        if traced != candidates[:len(traced)]:
            raise ValueError("auto fallback trace is not an ordered candidate prefix")
        if executions:
            if len(traced) == len(candidates):
                raise ValueError("auto cannot execute after every candidate was rejected")
            if executions[0]["engine_instance_id"] != candidates[len(traced)]:
                raise ValueError("auto execution does not follow fallback trace")
        elif value["status"] != "cancelled" and traced != candidates:
            raise ValueError("auto failure must account for every candidate")
        if set(traced) & {item["engine_instance_id"] for item in executions}:
            raise ValueError("rejected candidate appears as execution")
    if mode != "auto" and value["fallback_trace"]:
        raise ValueError("fallback trace outside auto mode")
    if mode != "compare" and value["comparison"]:
        raise ValueError("comparison outside compare mode")

    if producer:
        _reject_unrecognized_fields(value, RESULT_FIELDS, "run result")
        for execution in executions:
            _reject_unrecognized_fields(execution, EXECUTION_FIELDS, "backend execution")
        for rejection in value["fallback_trace"]:
            _reject_unrecognized_fields(rejection, FALLBACK_FIELDS, "fallback rejection")
        _require_namespaced_keys(value["metrics_summary"], "metrics_summary")


def _validate_terminal_error(value, producer=True):
    if value["status"] == "succeeded":
        if value["error"] is not None: raise ValueError("successful result cannot contain an error")
        return
    if not isinstance(value["error"], dict): raise ValueError("failed/cancelled result requires an error")
    validate_platform_error(value["error"], producer=producer)
    if value["status"] == "cancelled" and value["error"]["category"] != "Cancelled": raise ValueError("cancelled result requires Cancelled")
    if value["status"] == "failed" and value["error"]["category"] == "Cancelled": raise ValueError("failed result cannot use Cancelled")
