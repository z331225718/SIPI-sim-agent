"""Cross-field checks for M1-03 resource, event, and validation contracts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
SCHEMAS = {name: json.loads((ROOT / "schemas" / name).read_text()) for name in ("run-event.v1.schema.json", "engine-capabilities.v1.schema.json", "validation-report.v1.schema.json")}
RESOLVER = {name: RefResolver(base_uri=(ROOT / "schemas/").as_uri() + "/", referrer=schema) for name, schema in SCHEMAS.items()}
RESOURCE_FIELDS = ("wall_time_s", "cpu_time_s", "memory_bytes", "process_count", "artifact_bytes")


def validate_event(event, prior_by_run=None, producer=True):
    Draft202012Validator(SCHEMAS["run-event.v1.schema.json"], resolver=RESOLVER["run-event.v1.schema.json"]).validate(event)
    scope = event["scope"]
    expected = {"project": (None, None, None), "analysis": ("value", None, None), "attempt": ("value", "value", None), "backend_execution": ("value", "value", "value")}[scope]
    for field, required in zip(("analysis_id", "attempt_id", "backend_execution_id"), expected):
        if (event[field] is None) != (required is None): raise ValueError("event scope identity mismatch")
    if prior_by_run is not None and event["run_id"] in prior_by_run:
        sequence, elapsed = prior_by_run[event["run_id"]]
        if event["sequence"] <= sequence or event["elapsed_s"] < elapsed: raise ValueError("event order regression")
    if prior_by_run is not None: prior_by_run[event["run_id"]] = (event["sequence"], event["elapsed_s"])
    if producer:
        allowed = {"schema", "run_id", "sequence", "scope", "stage", "elapsed_s", "analysis_id", "attempt_id", "backend_execution_id", "progress", "domain_event_schema", "domain_event", "extensions"}
        extra = set(event) - allowed
        if extra: raise ValueError("event has unnamespaced fields")


def validate_resource_slice(parent, child, enforcement):
    if child["enforcement"] != parent["enforcement"]: raise ValueError("resource enforcement mismatch")
    for field in RESOURCE_FIELDS:
        if parent[field] is None and child[field] is not None: raise ValueError("resource slice invents parent limit")
        if parent[field] is not None and child[field] is None: raise ValueError("resource slice removes parent limit")
        if parent[field] is not None and child[field] is not None and child[field] > parent[field]: raise ValueError("resource slice exceeds parent limit")
        if child[field] is not None and (enforcement[field] != "hard" if child["enforcement"] == "required" else enforcement[field] == "unsupported"):
            raise ValueError("UnsupportedCapability")


def validate_resource_usage(limits, usage):
    actual = usage["actual_enforcement"]
    monitored = [field for field in RESOURCE_FIELDS if limits[field] is not None and actual[field] == "monitor"]
    for field in RESOURCE_FIELDS:
        if limits[field] is None: continue
        if limits["enforcement"] == "required" and actual[field] != "hard": raise ValueError("required usage must be hard")
        if limits["enforcement"] == "monitor" and actual[field] == "unsupported": raise ValueError("monitor usage cannot be unsupported")
    if monitored and ("sampling_period_s" not in usage or "max_possible_overshoot" not in usage): raise ValueError("monitor usage requires sampling and overshoot")
    if monitored and any(field not in usage["max_possible_overshoot"] or not isinstance(usage["max_possible_overshoot"][field], (int, float)) or usage["max_possible_overshoot"][field] < 0 for field in monitored): raise ValueError("monitor usage requires numeric per-resource overshoot")


def validate_platform_error(error, producer=True):
    category, resource = error["category"], error["resource"]
    if category == "Timeout" and resource != "wall_time_s": raise ValueError("Timeout must identify wall_time_s")
    if category == "ResourceLimit" and resource not in set(RESOURCE_FIELDS) - {"wall_time_s"}: raise ValueError("ResourceLimit must identify non-wall resource")
    if producer:
        extra = set(error) - {"category", "message", "resource", "cause", "details"}
        if extra: raise ValueError("platform error has unnamespaced fields")


def validate_validation_report(request, report, producer=True):
    Draft202012Validator(SCHEMAS["validation-report.v1.schema.json"], resolver=RESOLVER["validation-report.v1.schema.json"]).validate(report)
    for field in ("run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "selection_hash"):
        if report[field] != request[field]: raise ValueError(f"{field} mismatch")
    if report["valid"] == bool(report["errors"]): raise ValueError("validation valid/errors mismatch")
    for error in report["errors"]: validate_platform_error(error, producer=producer)
    if producer:
        extra = set(report) - {"schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "selection_hash", "valid", "errors", "warnings", "resource_enforcement", "extensions"}
        if extra: raise ValueError("validation report has unnamespaced fields")
    limits = request["resource_limits"]
    unavailable = [field for field in RESOURCE_FIELDS if limits[field] is not None and (report["resource_enforcement"][field] != "hard" if limits["enforcement"] == "required" else report["resource_enforcement"][field] == "unsupported")]
    if unavailable:
        if report["valid"]: raise ValueError("resource enforcement makes report invalid")
        if not any(error["category"] == "UnsupportedCapability" for error in report["errors"]): raise ValueError("resource enforcement requires UnsupportedCapability")


def validate_capabilities(value, producer=True):
    Draft202012Validator(SCHEMAS["engine-capabilities.v1.schema.json"], resolver=RESOLVER["engine-capabilities.v1.schema.json"]).validate(value)
    seen = set()
    for capability in value["capabilities"]:
        key = (capability["operation"], capability["payload_schema"], value["engine_instance_id"], capability["behavior_profile"], value["platform"]["os"], value["platform"]["architecture"], capability["execution_mode"])
        if key in seen: raise ValueError("duplicate capability key")
        seen.add(key)
    if producer:
        extra = set(value) - {"schema", "producer", "version", "build", "engine_instance_id", "bundle_hash", "platform", "capabilities", "extensions"}
        if extra: raise ValueError("capabilities has unnamespaced fields")
        if set(value["platform"]) - {"os", "architecture"}: raise ValueError("platform has unnamespaced fields")
        allowed = {"operation", "payload_schema", "domain_result_schemas", "behavior_profile", "role", "execution_mode", "resource_enforcement", "external_model_capabilities", "maximum_scale"}
        for capability in value["capabilities"]:
            if set(capability) - allowed: raise ValueError("capability has unnamespaced fields")


from sipi_contracts.validation.relations import (
    validate_capabilities, validate_event, validate_platform_error, validate_resource_slice,
    validate_resource_usage, validate_validation_report,
)
