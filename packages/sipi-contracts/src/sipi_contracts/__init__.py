"""Immutable, schema-first bindings for SIPI platform contracts."""

from .errors import ContractViolation
from .models import (
    BackendExecutionRequestV1,
    BackendExecutionResultV1,
    EngineCapabilitiesV1,
    RunRequestV1,
    RunResultV1,
    SipiArtifactRefV1,
    SipiRunEventV1,
    ValidationReportV1,
    ProvenanceV1,
    parse_artifact_ref,
    parse_backend_execution_request,
    parse_backend_execution_result,
    parse_engine_capabilities,
    parse_provenance,
    parse_run_event,
    parse_run_request,
    parse_run_result,
    parse_validation_report,
    validate_backend_execution_request,
    validate_backend_execution_result,
    validate_run_result,
)
from .validation import resolve_artifact_path

__all__ = [
    "BackendExecutionRequestV1", "BackendExecutionResultV1", "ContractViolation",
    "EngineCapabilitiesV1", "ProvenanceV1", "RunRequestV1", "RunResultV1", "SipiArtifactRefV1",
    "SipiRunEventV1", "parse_artifact_ref", "parse_backend_execution_request",
    "ValidationReportV1", "parse_backend_execution_result", "parse_engine_capabilities",
    "parse_provenance", "parse_run_event", "parse_run_request", "parse_run_result",
    "parse_validation_report", "resolve_artifact_path", "validate_backend_execution_request",
    "validate_backend_execution_result", "validate_run_result",
]
