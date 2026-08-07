from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import ContractViolation
from .registry import validate_definition, validate_wire
from .paths import portable_artifact_path_key


RESOURCE_FIELDS = ("wall_time_s", "cpu_time_s", "memory_bytes", "process_count", "artifact_bytes")
ARTIFACT_FIELDS = {"schema", "content_schema", "relative_path", "mime_type", "sha256", "byte_length", "producer", "role", "shape", "dtype", "byte_order", "layout", "extensions"}
PROVENANCE_FIELDS = {"producers", "request", "environment", "randomness", "policies", "extensions"}
PRODUCER_FIELDS = {"id", "kind", "name", "version", "commit", "build_profile", "dirty", "bundle_hash", "parent_ids"}
REQUIRED_PRODUCER_KINDS = {"platform", "adapter", "engine", "algorithm"}
PROVENANCE_SCHEMA_ID = "sipi.run-result.v1#/provenance"
_ATTEMPT_CONTROL_PATHS = {"success-manifest.json", "checksums.json", "run-record.json"}


def _violation(schema_id: str, code: str, message: str, pointer: str = "") -> None:
    raise ContractViolation(schema_id, code, pointer, message)


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], schema_id: str, description: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        _violation(schema_id, "unknown_field", f"{description} has unnamespaced fields: {sorted(unknown)}")


def validate_artifact_ref(value: Mapping[str, Any], *, producer: bool = True, provenance: Mapping[str, Any] | None = None) -> None:
    validate_wire("artifact-ref.v1.schema.json", value)
    if value["relative_path"].endswith("/"):
        _violation("sipi.artifact-ref.v1", "path", "artifact relative path must name a file", "/relative_path")
    dtype = value.get("dtype")
    byte_order = value.get("byte_order")
    if dtype in {"bool", "int8", "uint8"} and byte_order != "not_applicable":
        _violation("sipi.artifact-ref.v1", "array", "single-byte dtype requires not_applicable byte order")
    if dtype not in {None, "bool", "int8", "uint8"} and byte_order == "not_applicable":
        _violation("sipi.artifact-ref.v1", "array", "multi-byte dtype requires byte order")
    if producer:
        _reject_unknown(value, ARTIFACT_FIELDS, "sipi.artifact-ref.v1", "artifact")
    if provenance is not None and value["producer"] not in {item["id"] for item in provenance["producers"]}:
        _violation("sipi.artifact-ref.v1", "producer", "artifact producer is absent from provenance", "/producer")


def validate_artifact_collection(values: list[Mapping[str, Any]], *, producer: bool = True, provenance: Mapping[str, Any] | None = None) -> None:
    paths = [item["relative_path"] for item in values]
    if len(paths) != len(set(paths)):
        _violation("sipi.artifact-ref.v1", "duplicate_path", "duplicate artifact relative path")
    for item in values:
        validate_artifact_ref(item, producer=producer, provenance=provenance)


def _validate_publishable_artifact_collection(values: list[Mapping[str, Any]]) -> None:
    paths = [portable_artifact_path_key(item["relative_path"]) for item in values]
    if len(paths) != len(set(paths)):
        _violation("sipi.artifact-ref.v1", "duplicate_path", "duplicate portable artifact relative path")


def _validate_no_control_artifacts(values: list[Mapping[str, Any]], schema_id: str) -> None:
    paths = {portable_artifact_path_key(artifact["relative_path"]) for artifact in values}
    if _ATTEMPT_CONTROL_PATHS & paths:
        _violation(schema_id, "control_artifact", "artifacts cannot include attempt control files")


def validate_run_record_intrinsic(value: Mapping[str, Any]) -> None:
    validate_wire("run-record.v1.schema.json", value)
    if value["status"] == "succeeded":
        if value["error"] is not None:
            _violation("sipi.run-record.v1", "terminal_state", "succeeded record cannot contain an error")
    else:
        error = value["error"]
        assert isinstance(error, Mapping)
        validate_platform_error(error)
        if value["status"] == "cancelled" and error["category"] != "Cancelled":
            _violation("sipi.run-record.v1", "terminal_state", "cancelled record requires Cancelled")
        if value["status"] == "failed" and error["category"] == "Cancelled":
            _violation("sipi.run-record.v1", "terminal_state", "failed record cannot use Cancelled")
    validate_artifact_collection(value["artifacts"])
    _validate_publishable_artifact_collection(value["artifacts"])
    _validate_no_control_artifacts(value["artifacts"], "sipi.run-record.v1")


def validate_success_manifest_intrinsic(value: Mapping[str, Any]) -> None:
    validate_wire("success-manifest.v1.schema.json", value)
    validate_artifact_collection(value["artifacts"])
    _validate_publishable_artifact_collection(value["artifacts"])
    _validate_no_control_artifacts(value["artifacts"], "sipi.success-manifest.v1")


def validate_success_manifest_relation(run_record: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    validate_run_record_intrinsic(run_record)
    validate_success_manifest_intrinsic(manifest)
    if run_record["status"] != "succeeded":
        _violation("sipi.success-manifest.v1", "terminal_state", "only succeeded run records can publish success manifests")
    if tuple(run_record[field] for field in ("run_id", "analysis_id", "attempt_id")) != tuple(manifest[field] for field in ("run_id", "analysis_id", "attempt_id")):
        _violation("sipi.success-manifest.v1", "identity", "manifest identity must match run record")
    by_path = lambda artifacts: {portable_artifact_path_key(artifact["relative_path"]): artifact for artifact in artifacts}
    if by_path(run_record["artifacts"]) != by_path(manifest["artifacts"]):
        _violation("sipi.success-manifest.v1", "artifact_set", "manifest artifacts must equal the succeeded run record artifacts")


def validate_dag_node_record_intrinsic(value: Mapping[str, Any]) -> None:
    validate_wire("dag-node-record.v1.schema.json", value)
    blocked_by = value["blocked_by"]
    analysis_ids = [item["analysis_id"] for item in blocked_by]
    if len(analysis_ids) != len(set(analysis_ids)):
        _violation("sipi.dag-node-record.v1", "blocked_by", "blocked dependencies must be unique")
    if value["analysis_id"] in analysis_ids:
        _violation("sipi.dag-node-record.v1", "blocked_by", "blocked node cannot reference itself")


def validate_engine_lock_intrinsic(value: Mapping[str, Any]) -> None:
    validate_wire("engine-lock.v1.schema.json", value)
    engines = value["engines"]
    instance_ids = [engine["instance_id"] for engine in engines]
    if len(instance_ids) != len(set(instance_ids)):
        _violation("sipi.engine-lock.v1", "duplicate_instance", "engine instance IDs must be unique")
    instances = set(instance_ids)
    for engine in engines:
        if engine["bundle"]["kind"] == "local_path":
            portable_artifact_path_key(engine["bundle"]["path"])
            if engine["bundle"]["path"].endswith("/"):
                _violation("sipi.engine-lock.v1", "bundle_path", "bundle path must name a file")
        files = engine["bundle_manifest"]["files"]
        if engine["bundle_manifest"]["entrypoint"].endswith("/") or any(item["relative_path"].endswith("/") for item in files):
            _violation("sipi.engine-lock.v1", "bundle_file", "bundle manifest paths must name files")
        paths = [portable_artifact_path_key(item["relative_path"]) for item in files]
        if len(paths) != len(set(paths)):
            _violation("sipi.engine-lock.v1", "duplicate_bundle_file", "bundle manifest has duplicate portable paths")
        if portable_artifact_path_key(engine["bundle_manifest"]["entrypoint"]) not in set(paths):
            _violation("sipi.engine-lock.v1", "entrypoint", "bundle entrypoint must be listed in its manifest")
        entrypoints = [item for item in files if item["role"] == "entrypoint"]
        if len(entrypoints) != 1 or entrypoints[0]["relative_path"] != engine["bundle_manifest"]["entrypoint"]:
            _violation("sipi.engine-lock.v1", "entrypoint", "manifest requires one matching entrypoint file")
        runtime = engine["runtime"]
        if runtime["kind"] == "python" and not runtime["python_abi"]:
            _violation("sipi.engine-lock.v1", "runtime", "python runtime requires a Python ABI")
        if runtime["kind"] == "native" and not runtime["rust_target"]:
            _violation("sipi.engine-lock.v1", "runtime", "native runtime requires a Rust target")
        if runtime["kind"] == "hybrid" and (not runtime["python_abi"] or not runtime["rust_target"]):
            _violation("sipi.engine-lock.v1", "runtime", "hybrid runtime requires Python ABI and Rust target")
    for operation, selection in value["operation_defaults"].items():
        if operation not in {"circuit.solve.v1", "network.fit.v1", "link.simulate.v1", "com.r480.run.v1"}:
            _violation("sipi.engine-lock.v1", "operation", "default selection has an unknown operation")
        requested = ([selection["instance"]] if selection["mode"] == "strict" else selection["candidates"] if selection["mode"] == "auto" else [selection["reference"], selection["candidate"]])
        if not set(requested) <= instances:
            _violation("sipi.engine-lock.v1", "default_instance", "default selection references an unknown engine instance")
        if selection["mode"] == "compare" and selection["reference"] == selection["candidate"]:
            _violation("sipi.engine-lock.v1", "default_instance", "compare default requires distinct instances")


def validate_provenance(value: Mapping[str, Any], *, producer: bool = True) -> None:
    validate_definition("_defs/provenance.v1.schema.json", "provenance", value, PROVENANCE_SCHEMA_ID)
    producers = value["producers"]
    ids = [item["id"] for item in producers]
    if len(ids) != len(set(ids)):
        _violation(PROVENANCE_SCHEMA_ID, "duplicate_producer", "duplicate provenance producer id")
    by_id = {item["id"]: item for item in producers}
    for item in producers:
        if producer:
            _reject_unknown(item, PRODUCER_FIELDS, PROVENANCE_SCHEMA_ID, "provenance producer")
        for parent_id in item["parent_ids"]:
            if parent_id not in by_id:
                _violation(PROVENANCE_SCHEMA_ID, "missing_parent", "provenance parent is absent")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(producer_id: str) -> None:
        if producer_id in visiting:
            _violation(PROVENANCE_SCHEMA_ID, "producer_cycle", "provenance producer graph contains a cycle")
        if producer_id not in visited:
            visiting.add(producer_id)
            for parent_id in by_id[producer_id]["parent_ids"]:
                visit(parent_id)
            visiting.remove(producer_id)
            visited.add(producer_id)
    for producer_id in by_id:
        visit(producer_id)
    if producer:
        _reject_unknown(value, PROVENANCE_FIELDS, PROVENANCE_SCHEMA_ID, "provenance")
        if not REQUIRED_PRODUCER_KINDS <= {item["kind"] for item in producers}:
            _violation(PROVENANCE_SCHEMA_ID, "producer_kind", "provenance lacks a required producer kind")
        _reject_unknown(value["request"], {"schema", "behavior_profile", "inputs", "resolved_config_sha256"}, PROVENANCE_SCHEMA_ID, "provenance request")
        _reject_unknown(value["environment"], {"python", "rust", "os", "cpu", "blas", "thread_count", "dependency_locks"}, PROVENANCE_SCHEMA_ID, "provenance environment")
        _reject_unknown(value["randomness"], {"seed", "array_sources"}, PROVENANCE_SCHEMA_ID, "provenance randomness")
        policy_groups = {"fallback", "conditioning", "repairs", "truncations", "approximations"}
        _reject_unknown(value["policies"], policy_groups, PROVENANCE_SCHEMA_ID, "provenance policies")
        for item in value["request"]["inputs"] + value["environment"]["dependency_locks"]:
            _reject_unknown(item, {"name", "sha256"}, PROVENANCE_SCHEMA_ID, "provenance hash input")
        for item in value["randomness"]["array_sources"]:
            _reject_unknown(item, {"name", "source", "sha256"}, PROVENANCE_SCHEMA_ID, "provenance array source")
        for group in policy_groups:
            for item in value["policies"][group]:
                _reject_unknown(item, {"name", "parameters"}, PROVENANCE_SCHEMA_ID, "provenance policy")


def validate_platform_error(error: Mapping[str, Any], *, producer: bool = True) -> None:
    validate_definition("_defs/runtime-validation.v1.schema.json", "platform_error", error, "sipi.platform-error.v1")
    if error["category"] == "Timeout" and error["resource"] != "wall_time_s":
        _violation("sipi.platform-error.v1", "error_resource", "Timeout must identify wall_time_s")
    if error["category"] == "ResourceLimit" and error["resource"] not in set(RESOURCE_FIELDS) - {"wall_time_s"}:
        _violation("sipi.platform-error.v1", "error_resource", "ResourceLimit must identify non-wall resource")
    if producer:
        _reject_unknown(error, {"category", "message", "resource", "cause", "details"}, "sipi.platform-error.v1", "platform error")


def validate_resource_usage(limits: Mapping[str, Any], usage: Mapping[str, Any]) -> None:
    validate_definition("_defs/runtime-validation.v1.schema.json", "resource_limits", limits, "sipi.resource-limits.v1")
    validate_definition("_defs/runtime-validation.v1.schema.json", "resource_usage", usage, "sipi.resource-usage.v1")
    actual = usage["actual_enforcement"]
    monitored = [field for field in RESOURCE_FIELDS if limits[field] is not None and actual[field] == "monitor"]
    for field in RESOURCE_FIELDS:
        if limits[field] is None:
            continue
        if limits["enforcement"] == "required" and actual[field] != "hard":
            _violation("sipi.resource-usage.v1", "enforcement", "required usage must be hard")
        if limits["enforcement"] == "monitor" and actual[field] == "unsupported":
            _violation("sipi.resource-usage.v1", "enforcement", "monitor usage cannot be unsupported")
    if monitored and ("sampling_period_s" not in usage or "max_possible_overshoot" not in usage):
        _violation("sipi.resource-usage.v1", "monitoring", "monitor usage requires sampling and overshoot")
    if monitored and any(
        field not in usage["max_possible_overshoot"]
        or not isinstance(usage["max_possible_overshoot"][field], (int, float))
        or usage["max_possible_overshoot"][field] < 0
        for field in monitored
    ):
        _violation("sipi.resource-usage.v1", "monitoring", "monitor usage requires numeric per-resource overshoot")


def validate_resource_slice(parent: Mapping[str, Any], child: Mapping[str, Any], enforcement: Mapping[str, str]) -> None:
    validate_definition("_defs/runtime-validation.v1.schema.json", "resource_limits", parent, "sipi.resource-limits.v1")
    validate_definition("_defs/runtime-validation.v1.schema.json", "resource_limits", child, "sipi.resource-limits.v1")
    validate_definition("_defs/runtime-validation.v1.schema.json", "resource_enforcement", enforcement, "sipi.resource-enforcement.v1")
    if child["enforcement"] != parent["enforcement"]:
        _violation("sipi.resource-limits.v1", "slice", "resource enforcement mismatch")
    for field in RESOURCE_FIELDS:
        if parent[field] is None and child[field] is not None:
            _violation("sipi.resource-limits.v1", "slice", "resource slice invents parent limit")
        if parent[field] is not None and child[field] is None:
            _violation("sipi.resource-limits.v1", "slice", "resource slice removes parent limit")
        if parent[field] is not None and child[field] is not None and child[field] > parent[field]:
            _violation("sipi.resource-limits.v1", "slice", "resource slice exceeds parent limit")
        if child[field] is not None and (enforcement[field] != "hard" if child["enforcement"] == "required" else enforcement[field] == "unsupported"):
            _violation("sipi.resource-limits.v1", "enforcement", "UnsupportedCapability")


def validate_request(value: Mapping[str, Any], *, allow_internal: bool = False) -> None:
    validate_wire("run-request.v1.schema.json", value)
    selection = value["backend_selection"]
    if selection["mode"] == "compare" and selection["reference"] == selection["candidate"]:
        _violation("sipi.run-request.v1", "selection", "compare reference and candidate must differ")
    if selection["mode"] == "auto" and set(selection["fallback_on"]) != {"EngineUnavailable", "UnsupportedCapability"}:
        _violation("sipi.run-request.v1", "selection", "auto fallback reasons must be exactly the platform allowlist")
    if selection.get("allow_internal", False) and not allow_internal:
        _violation("sipi.run-request.v1", "internal_policy", "allow_internal requires authorized internal policy")
    if "payload_artifact" in value:
        validate_artifact_ref(value["payload_artifact"])


def validate_result(request: Mapping[str, Any], value: Mapping[str, Any], *, producer: bool = True, allow_internal: bool = False) -> None:
    validate_wire("run-result.v1.schema.json", value)
    validate_request(request, allow_internal=allow_internal)
    if "backend_execution_id" in value:
        _violation("sipi.run-result.v1", "orchestration", "backend_execution_id belongs to backend_executions")
    for field in ("run_id", "analysis_id", "attempt_id", "operation", "payload_schema"):
        if value[field] != request[field]:
            _violation("sipi.run-result.v1", "identity", f"{field} mismatch", f"/{field}")
    if value["selection_requested"] != request["backend_selection"]:
        _violation("sipi.run-result.v1", "selection", "selection mismatch")
    executions = value["backend_executions"]
    execution_ids = [item["backend_execution_id"] for item in executions]
    if len(execution_ids) != len(set(execution_ids)):
        _violation("sipi.run-result.v1", "duplicate_execution", "duplicate backend execution id")
    if value["status"] == "succeeded" and (not executions or any(item["status"] != "succeeded" for item in executions)):
        _violation("sipi.run-result.v1", "terminal_state", "successful result requires successful execution")
    _validate_terminal_error(value, producer)
    validate_resource_usage(request["resource_limits"], value["resource_usage"])
    validate_provenance(value["provenance"], producer=producer)
    artifacts = list(value["artifacts"])
    if "event_log_artifact" in value:
        artifacts.append(value["event_log_artifact"])
    for execution in executions:
        artifacts.extend(execution["artifacts"])
        _validate_terminal_error(execution, producer)
        _validate_execution_summary(execution)
    validate_artifact_collection(artifacts, producer=producer, provenance=value["provenance"])
    _validate_result_events(value, producer=producer)
    selection = request["backend_selection"]
    roles = [item["role"] for item in executions]
    if selection["mode"] == "compare":
        if sorted(roles) != ["candidate", "reference"]:
            _violation("sipi.run-result.v1", "selection", "compare roles")
        by_role = {item["role"]: item for item in executions}
        for role in ("reference", "candidate"):
            if by_role[role]["engine_instance_id"] != selection[role]:
                _violation("sipi.run-result.v1", "selection", f"compare {role} instance mismatch")
        if not value["comparison"] or value["comparison"].get("profile") != selection["comparison_profile"]:
            _violation("sipi.run-result.v1", "selection", "compare result requires matching comparison evidence")
    elif any(role != "primary" for role in roles):
        _violation("sipi.run-result.v1", "selection", "non-compare roles")
    elif selection["mode"] == "strict":
        if len(executions) > 1 or (executions and executions[0]["engine_instance_id"] != selection["instance"]):
            _violation("sipi.run-result.v1", "selection", "strict execution does not match selection")
    else:
        if len(executions) > 1:
            _violation("sipi.run-result.v1", "selection", "auto has multiple executions")
        traced = [item["instance"] for item in value["fallback_trace"]]
        candidates = selection["candidates"]
        if traced != candidates[:len(traced)]:
            _violation("sipi.run-result.v1", "selection", "auto fallback trace is not an ordered candidate prefix")
        if executions:
            if len(traced) == len(candidates) or executions[0]["engine_instance_id"] != candidates[len(traced)]:
                _violation("sipi.run-result.v1", "selection", "auto execution does not follow fallback trace")
        elif value["status"] != "cancelled" and traced != candidates:
            _violation("sipi.run-result.v1", "selection", "auto failure must account for every candidate")
        if set(traced) & {item["engine_instance_id"] for item in executions}:
            _violation("sipi.run-result.v1", "selection", "rejected candidate appears as execution")
    if selection["mode"] != "auto" and value["fallback_trace"]:
        _violation("sipi.run-result.v1", "selection", "fallback trace outside auto mode")
    if selection["mode"] != "compare" and value["comparison"]:
        _violation("sipi.run-result.v1", "selection", "comparison outside compare mode")
    if producer:
        _reject_unknown(value, {"schema", "run_id", "analysis_id", "attempt_id", "operation", "payload_schema", "status", "selection_requested", "backend_executions", "fallback_trace", "comparison", "metrics_summary", "artifacts", "events", "event_log_artifact", "provenance", "timings", "resource_usage", "error", "warnings", "extensions"}, "sipi.run-result.v1", "run result")
        for execution in executions:
            _reject_unknown(execution, {"backend_execution_id", "role", "engine_instance_id", "bundle_hash", "status", "domain_result_schema", "artifacts", "error"}, "sipi.run-result.v1", "backend execution")
        for rejection in value["fallback_trace"]:
            _reject_unknown(rejection, {"instance", "reason"}, "sipi.run-result.v1", "fallback rejection")
        invalid = [key for key in value["metrics_summary"] if "." not in key]
        if invalid:
            _violation("sipi.run-result.v1", "metrics", f"metrics_summary has unnamespaced keys: {sorted(invalid)}")


def validate_result_intrinsic(value: Mapping[str, Any], *, producer: bool = False) -> None:
    """Close every result invariant which does not require its originating request."""
    validate_wire("run-result.v1.schema.json", value)
    validate_provenance(value["provenance"], producer=producer)
    execution_ids = [item["backend_execution_id"] for item in value["backend_executions"]]
    if len(execution_ids) != len(set(execution_ids)):
        _violation("sipi.run-result.v1", "duplicate_execution", "duplicate backend execution id")
    _validate_terminal_error(value, producer)
    if value["status"] == "succeeded" and (not value["backend_executions"] or any(item["status"] != "succeeded" for item in value["backend_executions"])):
        _violation("sipi.run-result.v1", "terminal_state", "successful result requires successful execution")
    artifacts = list(value["artifacts"])
    if "event_log_artifact" in value:
        artifacts.append(value["event_log_artifact"])
    for execution in value["backend_executions"]:
        _validate_terminal_error(execution, producer)
        _validate_execution_summary(execution)
        artifacts.extend(execution["artifacts"])
    validate_artifact_collection(artifacts, producer=producer, provenance=value["provenance"])
    _validate_result_selection(value)
    _validate_result_events(value, producer=producer)
    if producer:
        _reject_unknown(value, {"schema", "run_id", "analysis_id", "attempt_id", "operation", "payload_schema", "status", "selection_requested", "backend_executions", "fallback_trace", "comparison", "metrics_summary", "artifacts", "events", "event_log_artifact", "provenance", "timings", "resource_usage", "error", "warnings", "extensions"}, "sipi.run-result.v1", "run result")
        for execution in value["backend_executions"]:
            _reject_unknown(execution, {"backend_execution_id", "role", "engine_instance_id", "bundle_hash", "status", "domain_result_schema", "artifacts", "error"}, "sipi.run-result.v1", "backend execution")
        invalid = [key for key in value["metrics_summary"] if "." not in key]
        if invalid:
            _violation("sipi.run-result.v1", "metrics", f"metrics_summary has unnamespaced keys: {sorted(invalid)}")
        for rejection in value["fallback_trace"]:
            _reject_unknown(rejection, {"instance", "reason"}, "sipi.run-result.v1", "fallback rejection")


def _validate_result_selection(value: Mapping[str, Any]) -> None:
    selection = value["selection_requested"]
    executions = value["backend_executions"]
    roles = [item["role"] for item in executions]
    if selection["mode"] == "compare":
        if sorted(roles) != ["candidate", "reference"]:
            _violation("sipi.run-result.v1", "selection", "compare roles")
        by_role = {item["role"]: item for item in executions}
        for role in ("reference", "candidate"):
            if by_role[role]["engine_instance_id"] != selection[role]:
                _violation("sipi.run-result.v1", "selection", f"compare {role} instance mismatch")
        if not value["comparison"] or value["comparison"].get("profile") != selection["comparison_profile"]:
            _violation("sipi.run-result.v1", "selection", "compare result requires matching comparison evidence")
    elif any(role != "primary" for role in roles):
        _violation("sipi.run-result.v1", "selection", "non-compare roles")
    elif selection["mode"] == "strict":
        if len(executions) > 1 or (executions and executions[0]["engine_instance_id"] != selection["instance"]):
            _violation("sipi.run-result.v1", "selection", "strict execution does not match selection")
    else:
        if len(executions) > 1:
            _violation("sipi.run-result.v1", "selection", "auto has multiple executions")
        traced = [item["instance"] for item in value["fallback_trace"]]
        candidates = selection["candidates"]
        if traced != candidates[:len(traced)]:
            _violation("sipi.run-result.v1", "selection", "auto fallback trace is not an ordered candidate prefix")
        if executions and (len(traced) == len(candidates) or executions[0]["engine_instance_id"] != candidates[len(traced)]):
            _violation("sipi.run-result.v1", "selection", "auto execution does not follow fallback trace")
        if not executions and value["status"] != "cancelled" and traced != candidates:
            _violation("sipi.run-result.v1", "selection", "auto failure must account for every candidate")
    if selection["mode"] != "auto" and value["fallback_trace"]:
        _violation("sipi.run-result.v1", "selection", "fallback trace outside auto mode")
    if selection["mode"] != "compare" and value["comparison"]:
        _violation("sipi.run-result.v1", "selection", "comparison outside compare mode")


def _validate_execution_summary(execution: Mapping[str, Any]) -> None:
    if execution["status"] == "succeeded" and (not execution["domain_result_schema"] or not execution["artifacts"]):
        _violation("sipi.run-result.v1", "terminal_state", "successful execution requires a domain result schema and artifact")


def _validate_result_events(value: Mapping[str, Any], *, producer: bool) -> None:
    prior: dict[str, tuple[int, float]] = {}
    backend_ids = {item["backend_execution_id"] for item in value["backend_executions"]}
    for event in value.get("events", []):
        validate_event(event, prior, producer=producer)
        if event["run_id"] != value["run_id"]:
            _violation("sipi.run-event.v1", "identity", "event run_id mismatch")
        if event["analysis_id"] is not None and event["analysis_id"] != value["analysis_id"]:
            _violation("sipi.run-event.v1", "identity", "event analysis_id mismatch")
        if event["attempt_id"] is not None and event["attempt_id"] != value["attempt_id"]:
            _violation("sipi.run-event.v1", "identity", "event attempt_id mismatch")
        if event["backend_execution_id"] is not None and event["backend_execution_id"] not in backend_ids:
            _violation("sipi.run-event.v1", "identity", "event backend_execution_id mismatch")


def _validate_terminal_error(value: Mapping[str, Any], producer: bool) -> None:
    if value["status"] == "succeeded":
        if value["error"] is not None:
            _violation("sipi.run-result.v1", "terminal_state", "successful result cannot contain an error")
        return
    if not isinstance(value["error"], Mapping):
        _violation("sipi.run-result.v1", "terminal_state", "failed/cancelled result requires an error")
    validate_platform_error(value["error"], producer=producer)
    if value["status"] == "cancelled" and value["error"]["category"] != "Cancelled":
        _violation("sipi.run-result.v1", "terminal_state", "cancelled result requires Cancelled")
    if value["status"] == "failed" and value["error"]["category"] == "Cancelled":
        _violation("sipi.run-result.v1", "terminal_state", "failed result cannot use Cancelled")


def validate_backend_request(run_request: Mapping[str, Any], value: Mapping[str, Any], expected_selection_hash: str, *, allow_internal: bool = False) -> None:
    validate_wire("backend-execution-request.v1.schema.json", value)
    validate_request(run_request, allow_internal=allow_internal)
    for field in ("run_id", "analysis_id", "attempt_id", "operation", "payload_schema"):
        if value[field] != run_request[field]:
            _violation("sipi.backend-execution-request.v1", "identity", f"{field} mismatch")
    for field in ("payload", "payload_artifact"):
        if (field in run_request) != (field in value) or (field in value and value[field] != run_request[field]):
            _violation("sipi.backend-execution-request.v1", "payload", "payload transport mismatch")
    if value["selection_hash"] != expected_selection_hash:
        _violation("sipi.backend-execution-request.v1", "selection_hash", "selection_hash mismatch")
    if "payload_artifact" in value:
        validate_artifact_ref(value["payload_artifact"])
    validate_artifact_collection(list(value["bound_inputs"].values()))
    selection = run_request["backend_selection"]
    if selection["mode"] in {"strict", "auto"} and value["role"] != "primary":
        _violation("sipi.backend-execution-request.v1", "selection", "strict/auto adapter role must be primary")
    if selection["mode"] == "strict" and value["engine_instance_id"] != selection["instance"]:
        _violation("sipi.backend-execution-request.v1", "selection", "strict instance mismatch")
    if selection["mode"] == "auto" and value["engine_instance_id"] not in selection["candidates"]:
        _violation("sipi.backend-execution-request.v1", "selection", "auto instance is not a resolved candidate")
    if selection["mode"] == "compare":
        if value["role"] not in {"reference", "candidate"}:
            _violation("sipi.backend-execution-request.v1", "selection", "compare adapter role must be reference or candidate")
        if value["engine_instance_id"] != selection[value["role"]]:
            _violation("sipi.backend-execution-request.v1", "selection", "compare role/instance mismatch")


def validate_backend_result(request: Mapping[str, Any], value: Mapping[str, Any], *, producer: bool = True) -> None:
    validate_wire("backend-execution-result.v1.schema.json", value)
    if {"backend_selection", "fallback_trace", "comparison"} & set(value):
        _violation("sipi.backend-execution-result.v1", "orchestration", "adapter result contains runtime orchestration fields")
    for field in ("run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema"):
        if value[field] != request[field]:
            _violation("sipi.backend-execution-result.v1", "identity", f"{field} mismatch")
    if value["status"] == "succeeded":
        if not value["domain_result_schema"]:
            _violation("sipi.backend-execution-result.v1", "terminal_state", "successful result requires a domain result schema")
        if value["error"] is not None:
            _violation("sipi.backend-execution-result.v1", "terminal_state", "successful result cannot contain an error")
        if "domain_result" not in value and not value["artifacts"]:
            _violation("sipi.backend-execution-result.v1", "terminal_state", "successful result requires an inline result or artifact")
    elif not isinstance(value["error"], Mapping):
        _violation("sipi.backend-execution-result.v1", "terminal_state", "failed/cancelled result requires an error object")
    if value["error"] is not None:
        validate_platform_error(value["error"], producer=producer)
        if value["status"] == "cancelled" and value["error"]["category"] != "Cancelled":
            _violation("sipi.backend-execution-result.v1", "terminal_state", "cancelled result requires Cancelled")
        if value["status"] == "failed" and value["error"]["category"] == "Cancelled":
            _violation("sipi.backend-execution-result.v1", "terminal_state", "failed result cannot use Cancelled")
    validate_resource_usage(request["resource_limits"], value["resource_usage"])
    validate_artifact_collection(value["artifacts"], producer=producer)
    _validate_backend_events(value, producer=producer)
    if "domain_result" in value and not value["domain_result_schema"]:
        _violation("sipi.backend-execution-result.v1", "domain_result", "inline domain result requires a domain result schema")
    if producer:
        _reject_unknown(value, {"schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "status", "domain_result_schema", "domain_result", "artifacts", "events", "warnings", "timings", "resource_usage", "error"}, "sipi.backend-execution-result.v1", "adapter result")


def validate_backend_result_intrinsic(value: Mapping[str, Any], *, producer: bool = False) -> None:
    validate_wire("backend-execution-result.v1.schema.json", value)
    if value["status"] == "succeeded":
        if not value["domain_result_schema"] or value["error"] is not None:
            _violation("sipi.backend-execution-result.v1", "terminal_state", "successful result requires schema and no error")
        if "domain_result" not in value and not value["artifacts"]:
            _violation("sipi.backend-execution-result.v1", "terminal_state", "successful result requires an inline result or artifact")
    elif not isinstance(value["error"], Mapping):
        _violation("sipi.backend-execution-result.v1", "terminal_state", "failed/cancelled result requires an error")
    if value["error"] is not None:
        validate_platform_error(value["error"], producer=producer)
        if value["status"] == "cancelled" and value["error"]["category"] != "Cancelled":
            _violation("sipi.backend-execution-result.v1", "terminal_state", "cancelled result requires Cancelled")
        if value["status"] == "failed" and value["error"]["category"] == "Cancelled":
            _violation("sipi.backend-execution-result.v1", "terminal_state", "failed result cannot use Cancelled")
    validate_artifact_collection(value["artifacts"], producer=producer)
    _validate_backend_events(value, producer=producer)
    if producer:
        _reject_unknown(value, {"schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "status", "domain_result_schema", "domain_result", "artifacts", "events", "warnings", "timings", "resource_usage", "error"}, "sipi.backend-execution-result.v1", "adapter result")


def _validate_backend_events(value: Mapping[str, Any], *, producer: bool) -> None:
    prior: dict[str, tuple[int, float]] = {}
    for event in value["events"]:
        validate_event(event, prior, producer=producer)
        if event["run_id"] != value["run_id"] or (event["analysis_id"] is not None and event["analysis_id"] != value["analysis_id"]) or (event["attempt_id"] is not None and event["attempt_id"] != value["attempt_id"]) or (event["backend_execution_id"] is not None and event["backend_execution_id"] != value["backend_execution_id"]):
            _violation("sipi.run-event.v1", "identity", "backend event identity mismatch")


def validate_validation_report_intrinsic(value: Mapping[str, Any], *, producer: bool = False) -> None:
    validate_wire("validation-report.v1.schema.json", value)
    if value["valid"] == bool(value["errors"]):
        _violation("sipi.validation-report.v1", "validity", "validation valid/errors mismatch")
    for error in value["errors"]:
        validate_platform_error(error, producer=producer)
    if producer:
        _reject_unknown(value, {"schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "selection_hash", "valid", "errors", "warnings", "resource_enforcement", "extensions"}, "sipi.validation-report.v1", "validation report")


def validate_event(value: Mapping[str, Any], prior_by_run: dict[str, tuple[int, float]] | None = None, *, producer: bool = True) -> None:
    validate_wire("run-event.v1.schema.json", value)
    expected = {"project": (None, None, None), "analysis": ("value", None, None), "attempt": ("value", "value", None), "backend_execution": ("value", "value", "value")}[value["scope"]]
    for field, required in zip(("analysis_id", "attempt_id", "backend_execution_id"), expected):
        if (value[field] is None) != (required is None):
            _violation("sipi.run-event.v1", "scope", "event scope identity mismatch")
    if prior_by_run is not None and value["run_id"] in prior_by_run:
        sequence, elapsed = prior_by_run[value["run_id"]]
        if value["sequence"] <= sequence or value["elapsed_s"] < elapsed:
            _violation("sipi.run-event.v1", "event_order", "event order regression")
    if prior_by_run is not None:
        prior_by_run[value["run_id"]] = (value["sequence"], value["elapsed_s"])
    if producer:
        _reject_unknown(value, {"schema", "run_id", "sequence", "scope", "stage", "elapsed_s", "analysis_id", "attempt_id", "backend_execution_id", "progress", "domain_event_schema", "domain_event", "extensions"}, "sipi.run-event.v1", "event")


def validate_validation_report(request: Mapping[str, Any], report: Mapping[str, Any], *, producer: bool = True) -> None:
    validate_wire("validation-report.v1.schema.json", report)
    for field in ("run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "selection_hash"):
        if report[field] != request[field]:
            _violation("sipi.validation-report.v1", "identity", f"{field} mismatch")
    if report["valid"] == bool(report["errors"]):
        _violation("sipi.validation-report.v1", "validity", "validation valid/errors mismatch")
    for error in report["errors"]:
        validate_platform_error(error, producer=producer)
    if producer:
        _reject_unknown(report, {"schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "selection_hash", "valid", "errors", "warnings", "resource_enforcement", "extensions"}, "sipi.validation-report.v1", "validation report")
    limits = request["resource_limits"]
    unavailable = [field for field in RESOURCE_FIELDS if limits[field] is not None and (report["resource_enforcement"][field] != "hard" if limits["enforcement"] == "required" else report["resource_enforcement"][field] == "unsupported")]
    if unavailable and (report["valid"] or not any(error["category"] == "UnsupportedCapability" for error in report["errors"])):
        _violation("sipi.validation-report.v1", "enforcement", "resource enforcement requires UnsupportedCapability")


def validate_capabilities(value: Mapping[str, Any], *, producer: bool = True) -> None:
    validate_wire("engine-capabilities.v1.schema.json", value)
    seen = set()
    for capability in value["capabilities"]:
        key = (capability["operation"], capability["payload_schema"], value["engine_instance_id"], capability["behavior_profile"], value["platform"]["os"], value["platform"]["architecture"], capability["execution_mode"])
        if key in seen:
            _violation("sipi.engine-capabilities.v1", "duplicate_capability", "duplicate capability key")
        seen.add(key)
    if producer:
        _reject_unknown(value, {"schema", "producer", "version", "build", "engine_instance_id", "bundle_hash", "platform", "capabilities", "extensions"}, "sipi.engine-capabilities.v1", "capabilities")
        _reject_unknown(value["platform"], {"os", "architecture"}, "sipi.engine-capabilities.v1", "platform")
        allowed = {"operation", "payload_schema", "domain_result_schemas", "behavior_profile", "role", "execution_mode", "resource_enforcement", "external_model_capabilities", "maximum_scale"}
        for capability in value["capabilities"]:
            _reject_unknown(capability, allowed, "sipi.engine-capabilities.v1", "capability")


def validate_capability_baseline(value: Mapping[str, Any]) -> None:
    """Validate a nonpublic, inspection-only M0 capability baseline."""
    validate_wire("capabilities-baseline.v1.schema.json", value)
    seen = set()
    for capability in value["capabilities"]:
        key = capability["key"]
        stable_key = (
            key["operation"], key["payload_schema"], key["engine_instance"],
            key["behavior_profile"], key["platform"]["os"],
            key["platform"]["architecture"], key["execution_mode"],
        )
        if stable_key in seen:
            _violation("sipi.capabilities-baseline.v1", "duplicate_capability", "duplicate baseline capability key")
        seen.add(stable_key)


def validate_capabilities_certified(value: Mapping[str, Any], *, producer: bool = False) -> None:
    """Validate the certified capability catalog consumed by the runtime."""
    validate_wire("capabilities-certified.v1.schema.json", value)
    seen = set()
    for entry in value["entries"]:
        key = (
            entry["operation"], entry["payload_schema"], entry["engine_instance"],
            entry["behavior_profile"], entry["platform"]["os"], entry["platform"]["architecture"],
            entry["execution_mode"],
        )
        if key in seen:
            _violation("sipi.capabilities-certified.v1", "duplicate_capability", "duplicate certified capability key")
        seen.add(key)
    if producer:
        _reject_unknown(value, {"schema", "status", "advertise", "capability_key_fields", "entries", "non_claims"}, "sipi.capabilities-certified.v1", "catalog")


def validate_project_intrinsic(value: Mapping[str, Any]) -> None:
    """Validate a sipi.project.v1 document plus its DAG declaration relations."""
    validate_wire("project.v1.schema.json", value)
    defaults = value["runtime"].get("backend_defaults", {})
    analyses = value["analyses"]
    ids = [analysis["id"] for analysis in analyses]
    if len(ids) != len(set(ids)):
        _violation("sipi.project.v1", "duplicate_analysis", "analysis IDs must be unique")
    declared = set(ids)
    for index, analysis in enumerate(analyses):
        pointer = f"/analyses/{index}"
        analysis_id = analysis["id"]
        if "backend_selection" not in analysis and analysis["operation"] not in defaults:
            _violation(
                "sipi.project.v1",
                "missing_selection",
                f"analysis {analysis_id} has no backend_selection and no runtime default for {analysis['operation']}",
                pointer,
            )
        for dependency in analysis.get("depends_on", []):
            if dependency == analysis_id:
                _violation("sipi.project.v1", "self_dependency", f"analysis cannot depend on itself: {analysis_id}", pointer)
            if dependency not in declared:
                _violation("sipi.project.v1", "unknown_dependency", f"depends_on references undeclared analysis: {dependency}", pointer)
        roles = [export["role"] for export in analysis.get("exports", [])]
        if len(roles) != len(set(roles)):
            _violation("sipi.project.v1", "duplicate_role", f"export roles must be unique for analysis {analysis_id}", pointer)
        for binding_name, binding in analysis.get("inputs", {}).items():
            binding_pointer = f"{pointer}/inputs/{binding_name}"
            source = binding["from_analysis"]
            if source == analysis_id:
                _violation("sipi.project.v1", "self_input", f"analysis cannot bind its own output: {analysis_id}", binding_pointer)
            if source not in declared:
                _violation("sipi.project.v1", "unknown_input_source", f"input binding references undeclared analysis: {source}", binding_pointer)
            source_exports = next(item for item in analyses if item["id"] == source).get("exports", [])
            matching_exports = [item for item in source_exports if item["role"] == binding["artifact_role"]]
            if not matching_exports:
                _violation(
                    "sipi.project.v1",
                    "missing_producer",
                    f"input binding has no producer export role {binding['artifact_role']} in {source}",
                    binding_pointer,
                )
            elif matching_exports[0]["schema"] != binding["expected_schema"]:
                _violation(
                    "sipi.project.v1",
                    "schema_mismatch",
                    f"input binding expected_schema does not match producer export schema for role {binding['artifact_role']}",
                    binding_pointer,
                )


def _axis_monotonicity(values: list[Any]) -> str:
    if len(values) < 2:
        return "non_monotonic"
    diffs = [values[index + 1] - values[index] for index in range(len(values) - 1)]
    if all(diff > 0 for diff in diffs):
        return "increasing"
    if all(diff < 0 for diff in diffs):
        return "decreasing"
    return "non_monotonic"


def validate_axis_intrinsic(value: Mapping[str, Any], *, producer: bool = True) -> None:
    """Validate a sipi.axis.v1 document plus its axis semantics."""
    validate_wire("axis.v1.schema.json", value)
    if producer:
        _reject_unknown(
            value,
            {"schema", "kind", "unit", "dtype", "length", "monotonicity", "uniform", "sample_location", "start", "step", "values", "values_artifact", "spectrum", "extensions"},
            "sipi.axis.v1",
            "axis",
        )
    kind = value["kind"]
    spectrum = value.get("spectrum")
    if kind == "frequency" and spectrum is None:
        _violation("sipi.axis.v1", "spectrum", "frequency axis requires spectrum metadata")
    if kind != "frequency" and spectrum is not None:
        _violation("sipi.axis.v1", "spectrum", "spectrum metadata is only valid for frequency axes")
    if "start" in value:
        if not value["uniform"]:
            _violation("sipi.axis.v1", "uniform", "start/step axis must declare uniform=true")
        if value["step"] == 0:
            _violation("sipi.axis.v1", "step", "axis step must be non-zero")
    if "values" in value:
        if value["uniform"]:
            _violation("sipi.axis.v1", "uniform", "explicit values axis must declare uniform=false")
        if len(value["values"]) != value["length"]:
            _violation("sipi.axis.v1", "length", "values length must equal declared length")
        declared = value["monotonicity"]
        computed = _axis_monotonicity(value["values"])
        if declared != "non_monotonic" and computed != declared:
            _violation("sipi.axis.v1", "monotonicity", f"declared {declared} but values are {computed}")
    if "values_artifact" in value:
        if value["uniform"]:
            _violation("sipi.axis.v1", "uniform", "values_artifact axis must declare uniform=false")
        validate_artifact_ref(value["values_artifact"], producer=producer)


def validate_port_map_intrinsic(value: Mapping[str, Any], *, producer: bool = True) -> None:
    """Validate a sipi.port-map.v1 document plus port relation semantics."""
    validate_wire("port-map.v1.schema.json", value)
    if producer:
        _reject_unknown(value, {"schema", "basis", "index_base", "ports", "extensions"}, "sipi.port-map.v1", "port map")
    ports = value["ports"]
    ids = [port["id"] for port in ports]
    if len(ids) != len(set(ids)):
        _violation("sipi.port-map.v1", "duplicate_id", "port ids must be unique")
    indexes = [port["external_index"] for port in ports]
    if len(indexes) != len(set(indexes)):
        _violation("sipi.port-map.v1", "duplicate_index", "external indexes must be unique")
    by_id = {port["id"]: port for port in ports}
    basis = value["basis"]
    for port in ports:
        port_id = port["id"]
        if "reference" in port:
            reference = port["reference"]
            if reference == port_id:
                _violation("sipi.port-map.v1", "self_reference", f"port cannot reference itself: {port_id}", f"/ports/{port_id}")
            if reference not in by_id:
                _violation("sipi.port-map.v1", "unknown_reference", f"port references undeclared node: {reference}", f"/ports/{port_id}")
        if "pair_with" in port:
            pair = port["pair_with"]
            if basis != "mixed_mode":
                _violation("sipi.port-map.v1", "pairing", "pair_with is only valid in mixed_mode basis", f"/ports/{port_id}")
            if port["kind"] != "signal":
                _violation("sipi.port-map.v1", "pairing", "only signal ports may declare pair_with", f"/ports/{port_id}")
            if pair == port_id:
                _violation("sipi.port-map.v1", "self_pair", f"port cannot pair with itself: {port_id}", f"/ports/{port_id}")
            if pair not in by_id:
                _violation("sipi.port-map.v1", "unknown_pair", f"port pairs with undeclared port: {pair}", f"/ports/{port_id}")
            if by_id[pair].get("pair_with") != port_id:
                _violation("sipi.port-map.v1", "asymmetric_pair", f"pair_with must be symmetric for {port_id} and {pair}", f"/ports/{port_id}")


def validate_network_tensor_intrinsic(value: Mapping[str, Any], *, producer: bool = True) -> None:
    """Validate a sipi.network-tensor.v1 document plus DTO composition semantics."""
    validate_wire("network-tensor.v1.schema.json", value)
    if producer:
        _reject_unknown(
            value,
            {"schema", "parameter_kind", "parameter_kind_name", "axis", "port_map", "data", "shape", "complex_encoding", "dtype", "byte_order", "layout", "z0", "wave_definition", "reader", "extensions"},
            "sipi.network-tensor.v1",
            "network tensor",
        )
    axis = value["axis"]
    if axis["kind"] != "frequency":
        _violation("sipi.network-tensor.v1", "axis", "network tensor axis must be a frequency axis")
    if axis["length"] != value["shape"]["frequency"]:
        _violation("sipi.network-tensor.v1", "shape", "shape.frequency must equal axis length")
    ports = value["port_map"]["ports"]
    port_count = sum(1 for port in ports if port["kind"] in {"signal", "common_mode"})
    output_ports = value["shape"]["output_ports"]
    input_ports = value["shape"]["input_ports"]
    if value["parameter_kind"] in {"S", "Y", "Z", "H"}:
        if output_ports != input_ports or output_ports != port_count:
            _violation("sipi.network-tensor.v1", "shape", f"{value['parameter_kind']} tensor must be square with {port_count} ports")
    else:
        if output_ports > port_count or input_ports > port_count:
            _violation("sipi.network-tensor.v1", "shape", "shape ports must not exceed declared ports")
    if value["parameter_kind"] == "EXT" and not value.get("parameter_kind_name"):
        _violation("sipi.network-tensor.v1", "parameter_kind", "EXT parameter kind requires parameter_kind_name")
    if value["dtype"] in {"complex128", "complex64"} and value["complex_encoding"] != "interleaved":
        _violation("sipi.network-tensor.v1", "complex", "complex dtype requires interleaved encoding")
    validate_artifact_ref(value["data"], producer=producer)
    z0 = value["z0"]
    if z0["kind"] == "scalar":
        if "value" not in z0:
            _violation("sipi.network-tensor.v1", "z0", "scalar z0 requires a positive value")
    else:
        if "values_artifact" not in z0:
            _violation("sipi.network-tensor.v1", "z0", f"{z0['kind']} z0 requires values_artifact")
        else:
            validate_artifact_ref(z0["values_artifact"], producer=producer)
    port_ids = {port["id"] for port in ports}
    reorders = value["reader"].get("port_reorder", [])
    from_ids = [item["from"] for item in reorders]
    to_ids = [item["to"] for item in reorders]
    if len(from_ids) != len(set(from_ids)) or len(to_ids) != len(set(to_ids)):
        _violation("sipi.network-tensor.v1", "port_reorder", "port reorder from/to must be unique")
    for item in reorders:
        if item["from"] == item["to"]:
            _violation("sipi.network-tensor.v1", "port_reorder", "port reorder cannot map a port to itself")
        if item["from"] not in port_ids or item["to"] not in port_ids:
            _violation("sipi.network-tensor.v1", "port_reorder", "port reorder references undeclared port")


def _validate_signal_document(value: Mapping[str, Any], schema_id: str, *, axis_kind: str, axis_length_key: str, producer: bool) -> None:
    validate_wire("waveform.v1.schema.json" if schema_id == "sipi.waveform.v1" else "spectrum.v1.schema.json", value)
    if producer:
        _reject_unknown(
            value,
            {
                "schema",
                "axis",
                "port_map",
                "signal_kind",
                "voltage_measurement",
                "current_sign_convention",
                "unit",
                "data",
                "shape",
                "channels",
                "fft",
                "sample_scaling",
                "effective_interval",
                "warmup_samples",
                "trimming",
                "initial_state",
                "extensions",
            },
            schema_id,
            "signal document",
        )
    if value["axis"]["kind"] != axis_kind:
        _violation(schema_id, "axis", f"axis kind must be {axis_kind}")
    if value["shape"][axis_length_key] != value["axis"]["length"]:
        _violation(schema_id, "shape", f"shape.{axis_length_key} must equal axis length")
    if value["shape"]["channels"] != len(value["channels"]):
        _violation(schema_id, "shape", "shape.channels must equal channels length")
    if value["signal_kind"] == "voltage":
        if "voltage_measurement" not in value:
            _violation(schema_id, "signal", "voltage signal requires voltage_measurement")
    else:
        if "current_sign_convention" not in value:
            _violation(schema_id, "signal", "current signal requires current_sign_convention")
    port_map_ports = value["port_map"]["ports"]
    by_id = {port["id"]: port for port in port_map_ports}
    for index, channel in enumerate(value["channels"]):
        pointer = f"/channels/{index}"
        port_id = channel["port_id"]
        if port_id not in by_id:
            _violation(schema_id, "channel", f"channel references undeclared port: {port_id}", pointer)
            continue
        if by_id[port_id]["polarity"] != channel["polarity"]:
            _violation(schema_id, "channel", f"channel polarity must match port map for {port_id}", pointer)
        reference = channel.get("reference")
        if reference is not None:
            if reference == port_id:
                _violation(schema_id, "channel", f"channel cannot reference itself: {port_id}", pointer)
            if reference not in by_id:
                _violation(schema_id, "channel", f"channel references undeclared node: {reference}", pointer)
    validate_artifact_ref(value["data"], producer=producer)
    if "fft" in value:
        _reject_unknown(value["fft"], {"normalization", "window", "scaling", "extensions"}, schema_id, "fft")


def validate_waveform_intrinsic(value: Mapping[str, Any], *, producer: bool = True) -> None:
    """Validate a sipi.waveform.v1 document plus signal semantics."""
    _validate_signal_document(value, "sipi.waveform.v1", axis_kind="time", axis_length_key="samples", producer=producer)
    samples = value["shape"]["samples"]
    interval = value.get("effective_interval")
    if interval is not None and not (0 <= interval["start_index"] < interval["end_index"] <= samples):
        _violation("sipi.waveform.v1", "interval", "effective_interval must lie within samples")
    warmup = value.get("warmup_samples", 0)
    trimming = value.get("trimming")
    trimmed = (trimming["leading_samples"] + trimming["trailing_samples"]) if trimming is not None else 0
    if warmup + trimmed > samples:
        _violation("sipi.waveform.v1", "interval", "warmup plus trimming must not exceed samples")


def validate_spectrum_intrinsic(value: Mapping[str, Any], *, producer: bool = True) -> None:
    """Validate a sipi.spectrum.v1 document plus signal semantics."""
    _validate_signal_document(value, "sipi.spectrum.v1", axis_kind="frequency", axis_length_key="bins", producer=producer)


def validate_channel_resolution_policy_intrinsic(value: Mapping[str, Any], *, producer: bool = True) -> None:
    """Validate a sipi.channel-resolution-policy.v1 document."""
    validate_wire("channel-resolution-policy.v1.schema.json", value)
    if producer:
        _reject_unknown(
            value,
            {"schema", "reader_semantics", "port_selection", "termination", "interpolation", "dc", "causality", "ifft", "normalization", "output", "extensions"},
            "sipi.channel-resolution-policy.v1",
            "resolution policy",
        )
    port_ids = [item["port_id"] for item in value["port_selection"]]
    if len(port_ids) != len(set(port_ids)):
        _violation("sipi.channel-resolution-policy.v1", "port_selection", "selected port ids must be unique")
    output = value["output"]
    if output["signal_intent"] == "voltage" and "current_to_voltage_sign" not in output:
        _violation("sipi.channel-resolution-policy.v1", "output", "voltage output requires current_to_voltage_sign")
    reference_port = output.get("reference_port")
    if reference_port is not None and reference_port not in port_ids:
        _violation("sipi.channel-resolution-policy.v1", "output", "output reference_port must be a selected port")


def validate_transform_policy_intrinsic(value: Mapping[str, Any], *, producer: bool = True) -> None:
    """Validate a sipi.transform-policy.v1 document (explicit implementation-named transforms).

    The platform pins the ordered transform chain and public semantic fields only;
    algorithm details and format parsing remain with the domain owner.  Port
    transforms may repeat as an explicit sequence; numeric transform kinds
    (interpolation/dc/causality/passivity) are single-step per chain so their
    order is unambiguous.
    """
    validate_wire("transform-policy.v1.schema.json", value)
    if producer:
        _reject_unknown(value, {"schema", "reader_semantics", "transforms", "extensions"}, "sipi.transform-policy.v1", "transform policy")
    numeric_kinds = {"interpolation", "dc", "causality", "passivity"}
    seen_numeric: set[str] = set()
    for index, transform in enumerate(value["transforms"]):
        pointer = f"/transforms/{index}"
        kind = transform["kind"]
        parameters = transform["parameters"]
        if kind in numeric_kinds:
            if kind in seen_numeric:
                _violation("sipi.transform-policy.v1", "duplicate_transform", f"numeric transform kind {kind} must appear at most once", pointer)
            seen_numeric.add(kind)
        if kind == "port":
            operation = parameters.get("operation")
            if operation is None:
                _violation("sipi.transform-policy.v1", "port_transform", "port transform requires an explicit operation", pointer)
            elif operation != "identity" and "ports" not in parameters:
                _violation("sipi.transform-policy.v1", "port_transform", f"port operation {operation} requires the affected ports", pointer)
        elif kind == "interpolation" and "method" not in parameters:
            _violation("sipi.transform-policy.v1", "interpolation", "interpolation transform requires a method", pointer)
        elif kind == "dc" and "method" not in parameters:
            _violation("sipi.transform-policy.v1", "dc", "dc transform requires a method", pointer)
        elif kind == "causality" and "method" not in parameters:
            _violation("sipi.transform-policy.v1", "causality", "causality transform requires a method", pointer)


def validate_channel_resolution_report_intrinsic(value: Mapping[str, Any], *, producer: bool = False) -> None:
    """Validate a sipi.channel-resolution-report.v1 document (tolerant consumer)."""
    validate_wire("channel-resolution-report.v1.schema.json", value)
    kinds = [item["kind"] for item in value["transforms"]]
    if len(kinds) != len(set(kinds)):
        _violation("sipi.channel-resolution-report.v1", "transforms", "transform kinds must be unique")
