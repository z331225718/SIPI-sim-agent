from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar
from collections.abc import Mapping
from types import MappingProxyType

from .errors import ContractViolation
from .json_types import JsonValue, freeze_json, load_json, thaw_json
from .validation.relations import (
    validate_artifact_ref,
    validate_backend_request,
    validate_backend_result,
    validate_event,
    validate_provenance,
    validate_request,
    validate_result_intrinsic,
    validate_backend_result_intrinsic,
    validate_capabilities,
    validate_capability_baseline,
    validate_validation_report_intrinsic,
)
from .validation.registry import schema_id_for, validate_wire


@dataclass(frozen=True, slots=True, init=False)
class ContractModel:
    """Immutable contract value which always round-trips its original wire data."""

    _data: Mapping[str, JsonValue]
    schema_name: ClassVar[str]
    known_fields: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("contract models must be created with a parse_* factory")

    @classmethod
    def _from_frozen(cls, data: Mapping[str, JsonValue]) -> "ContractModel":
        instance = object.__new__(cls)
        object.__setattr__(instance, "_data", data)
        return instance

    @property
    def schema_id(self) -> str:
        return schema_id_for(self.schema_name)

    @property
    def wire(self) -> Mapping[str, JsonValue]:
        return self._data

    @property
    def extra(self) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: value for key, value in self._data.items() if key not in self.known_fields})

    def to_wire(self) -> dict[str, Any]:
        return thaw_json(self._data)

    def __getitem__(self, key: str) -> JsonValue:
        return self._data[key]


def _mapping(value: str | Mapping[str, Any], schema_name: str) -> Mapping[str, Any]:
    schema_id = schema_id_for(schema_name)
    if isinstance(value, str):
        return load_json(value, schema_id)
    if not isinstance(value, Mapping):
        raise ContractViolation(schema_id, "type", "", "contract root must be an object")
    return value


def _parse(model_type: type[ContractModel], value: str | Mapping[str, Any]) -> ContractModel:
    data = _mapping(value, model_type.schema_name)
    validate_wire(model_type.schema_name, data)
    frozen = freeze_json(data, schema_id_for(model_type.schema_name))
    assert isinstance(frozen, Mapping)
    return model_type._from_frozen(frozen)


@dataclass(frozen=True, slots=True, init=False)
class RunRequestV1(ContractModel):
    schema_name = "run-request.v1.schema.json"
    known_fields = frozenset({"schema", "run_id", "project_id", "analysis_id", "attempt_id", "operation", "payload_schema", "payload", "payload_artifact", "backend_selection", "resource_limits", "randomness", "artifact_policy", "extensions"})


@dataclass(frozen=True, slots=True, init=False)
class RunResultV1(ContractModel):
    schema_name = "run-result.v1.schema.json"
    known_fields = frozenset({"schema", "run_id", "analysis_id", "attempt_id", "operation", "payload_schema", "status", "selection_requested", "backend_executions", "fallback_trace", "comparison", "metrics_summary", "artifacts", "events", "event_log_artifact", "provenance", "timings", "resource_usage", "error", "warnings", "extensions"})


@dataclass(frozen=True, slots=True, init=False)
class BackendExecutionRequestV1(ContractModel):
    schema_name = "backend-execution-request.v1.schema.json"
    known_fields = frozenset({"schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "payload", "payload_artifact", "bound_inputs", "resource_limits", "artifact_policy", "randomness", "selection_hash"})


@dataclass(frozen=True, slots=True, init=False)
class BackendExecutionResultV1(ContractModel):
    schema_name = "backend-execution-result.v1.schema.json"
    known_fields = frozenset({"schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "status", "domain_result_schema", "domain_result", "artifacts", "events", "warnings", "timings", "resource_usage", "error"})


@dataclass(frozen=True, slots=True, init=False)
class SipiRunEventV1(ContractModel):
    schema_name = "run-event.v1.schema.json"
    known_fields = frozenset({"schema", "run_id", "sequence", "scope", "stage", "elapsed_s", "analysis_id", "attempt_id", "backend_execution_id", "progress", "domain_event_schema", "domain_event", "extensions"})


@dataclass(frozen=True, slots=True, init=False)
class SipiArtifactRefV1(ContractModel):
    schema_name = "artifact-ref.v1.schema.json"
    known_fields = frozenset({"schema", "content_schema", "relative_path", "mime_type", "sha256", "byte_length", "producer", "role", "shape", "dtype", "byte_order", "layout", "extensions"})


@dataclass(frozen=True, slots=True, init=False)
class ProvenanceV1(ContractModel):
    schema_name = "_defs/provenance.v1.schema.json"
    known_fields = frozenset({"producers", "request", "environment", "randomness", "policies", "extensions"})


@dataclass(frozen=True, slots=True, init=False)
class EngineCapabilitiesV1(ContractModel):
    schema_name = "engine-capabilities.v1.schema.json"
    known_fields = frozenset({"schema", "producer", "version", "build", "engine_instance_id", "bundle_hash", "platform", "capabilities", "extensions"})


@dataclass(frozen=True, slots=True, init=False)
class ValidationReportV1(ContractModel):
    schema_name = "validation-report.v1.schema.json"
    known_fields = frozenset({"schema", "run_id", "analysis_id", "attempt_id", "backend_execution_id", "role", "engine_instance_id", "bundle_hash", "operation", "payload_schema", "selection_hash", "valid", "errors", "warnings", "resource_enforcement", "extensions"})


@dataclass(frozen=True, slots=True, init=False)
class PythonCapabilityBaselineV1(ContractModel):
    """Nonpublic quality binding; it intentionally has no runtime selection API."""

    schema_name = "capabilities-baseline.v1.schema.json"
    known_fields = frozenset({"schema", "status", "runtime_consumable", "advertise", "default_auto_eligible", "source", "capability_key_fields", "catalogs", "capabilities", "unmapped_capability_gaps", "non_claims"})


def parse_run_request(value: str | Mapping[str, Any], *, allow_internal: bool = False) -> RunRequestV1:
    data = _mapping(value, RunRequestV1.schema_name)
    validate_request(data, allow_internal=allow_internal)
    return _parse(RunRequestV1, data)  # type: ignore[return-value]


def parse_run_result(value: str | Mapping[str, Any], *, producer: bool = False) -> RunResultV1:
    data = _mapping(value, RunResultV1.schema_name)
    validate_result_intrinsic(data, producer=producer)
    return _parse(RunResultV1, data)  # type: ignore[return-value]


def parse_backend_execution_request(value: str | Mapping[str, Any]) -> BackendExecutionRequestV1:
    data = _mapping(value, BackendExecutionRequestV1.schema_name)
    validate_wire(BackendExecutionRequestV1.schema_name, data)
    if "payload_artifact" in data:
        validate_artifact_ref(data["payload_artifact"])
    from .validation.relations import validate_artifact_collection
    validate_artifact_collection(list(data["bound_inputs"].values()))
    return _parse(BackendExecutionRequestV1, data)  # type: ignore[return-value]


def parse_backend_execution_result(value: str | Mapping[str, Any], *, producer: bool = False) -> BackendExecutionResultV1:
    data = _mapping(value, BackendExecutionResultV1.schema_name)
    validate_backend_result_intrinsic(data, producer=producer)
    return _parse(BackendExecutionResultV1, data)  # type: ignore[return-value]


def parse_run_event(value: str | Mapping[str, Any], *, producer: bool = False) -> SipiRunEventV1:
    data = _mapping(value, SipiRunEventV1.schema_name)
    validate_event(data, producer=producer)
    return _parse(SipiRunEventV1, data)  # type: ignore[return-value]


def parse_artifact_ref(value: str | Mapping[str, Any], *, producer: bool = False) -> SipiArtifactRefV1:
    data = _mapping(value, SipiArtifactRefV1.schema_name)
    validate_artifact_ref(data, producer=producer)
    return _parse(SipiArtifactRefV1, data)  # type: ignore[return-value]


def parse_provenance(value: str | Mapping[str, Any], *, producer: bool = False) -> ProvenanceV1:
    data = _mapping(value, ProvenanceV1.schema_name)
    validate_provenance(data, producer=producer)
    frozen = freeze_json(data, "sipi.run-result.v1#/provenance")
    assert isinstance(frozen, Mapping)
    return ProvenanceV1._from_frozen(frozen)  # type: ignore[return-value]


def parse_engine_capabilities(value: str | Mapping[str, Any], *, producer: bool = False) -> EngineCapabilitiesV1:
    data = _mapping(value, EngineCapabilitiesV1.schema_name)
    validate_capabilities(data, producer=producer)
    return _parse(EngineCapabilitiesV1, data)  # type: ignore[return-value]


def parse_capability_baseline(value: str | Mapping[str, Any]) -> PythonCapabilityBaselineV1:
    data = _mapping(value, PythonCapabilityBaselineV1.schema_name)
    validate_capability_baseline(data)
    return _parse(PythonCapabilityBaselineV1, data)  # type: ignore[return-value]


def parse_validation_report(value: str | Mapping[str, Any], *, producer: bool = False) -> ValidationReportV1:
    data = _mapping(value, ValidationReportV1.schema_name)
    validate_validation_report_intrinsic(data, producer=producer)
    return _parse(ValidationReportV1, data)  # type: ignore[return-value]


def validate_run_result(request: RunRequestV1, result: RunResultV1, *, producer: bool = True, allow_internal: bool = False) -> None:
    from .validation.relations import validate_result
    validate_result(request.to_wire(), result.to_wire(), producer=producer, allow_internal=allow_internal)


def validate_backend_execution_result(request: BackendExecutionRequestV1, result: BackendExecutionResultV1, *, producer: bool = True) -> None:
    validate_backend_result(request.to_wire(), result.to_wire(), producer=producer)


def validate_backend_execution_request(run_request: RunRequestV1, request: BackendExecutionRequestV1, expected_selection_hash: str, *, allow_internal: bool = False) -> None:
    validate_backend_request(run_request.to_wire(), request.to_wire(), expected_selection_hash, allow_internal=allow_internal)
