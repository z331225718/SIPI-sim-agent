"""Adapter capability declarations and request preflight (M2-11 prerequisite)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sipi_contracts import BackendExecutionRequestV1, EngineCapabilitiesV1, parse_engine_capabilities

from .spi import UnsupportedCapabilityError

RESOURCE_FIELDS = ("wall_time_s", "cpu_time_s", "memory_bytes", "process_count", "artifact_bytes")


@dataclass(frozen=True)
class AdapterCapability:
    operation: str
    payload_schema: str
    domain_result_schemas: tuple[str, ...]
    behavior_profile: str
    role: str
    execution_mode: str
    resource_enforcement: Mapping[str, str] = field(default_factory=lambda: {name: "unsupported" for name in RESOURCE_FIELDS})
    external_model_capabilities: Mapping[str, Any] = field(default_factory=dict)
    maximum_scale: Mapping[str, float] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "payload_schema": self.payload_schema,
            "domain_result_schemas": list(self.domain_result_schemas),
            "behavior_profile": self.behavior_profile,
            "role": self.role,
            "execution_mode": self.execution_mode,
            "resource_enforcement": dict(self.resource_enforcement),
            "external_model_capabilities": dict(self.external_model_capabilities),
            "maximum_scale": dict(self.maximum_scale),
        }


def preflight(
    request: BackendExecutionRequestV1,
    entries: tuple[AdapterCapability, ...],
    *,
    platform_enforcement: Mapping[str, str] | None = None,
) -> None:
    """Reject unsupported operations/payloads and uncertified hard enforcement.

    Required limits are satisfiable when the managed-worker platform layer
    provides hard enforcement for the field (``platform_enforcement``) or an
    adapter capability is certified hard for it; otherwise fail closed.
    """
    wire = request.to_wire()
    matched = [entry for entry in entries if entry.operation == wire["operation"] and entry.payload_schema == wire["payload_schema"]]
    if not matched:
        raise UnsupportedCapabilityError(
            f"adapter does not support {wire['operation']}/{wire['payload_schema']}"
        )
    limits = wire["resource_limits"]
    if limits.get("enforcement") == "required":
        platform_hard = {name: mode for name, mode in (platform_enforcement or {}).items() if mode == "hard"}
        for field_name in RESOURCE_FIELDS:
            if limits.get(field_name) is not None and field_name not in platform_hard and not any(entry.resource_enforcement.get(field_name) == "hard" for entry in matched):
                raise UnsupportedCapabilityError(f"{field_name} requires certified hard enforcement")


def build_engine_capabilities(
    *,
    engine_instance_id: str,
    bundle_hash: str,
    entries: tuple[AdapterCapability, ...],
    producer: str = "sipi-adapters",
    version: str = "1",
    build: str = "m2-slice",
    os_name: str = "windows",
    architecture: str = "x86_64",
) -> EngineCapabilitiesV1:
    wire = {
        "schema": "sipi.engine-capabilities.v1",
        "producer": producer,
        "version": version,
        "build": build,
        "engine_instance_id": engine_instance_id,
        "bundle_hash": bundle_hash,
        "platform": {"os": os_name, "architecture": architecture},
        "capabilities": [entry.to_wire() for entry in entries],
        "extensions": {},
    }
    return parse_engine_capabilities(wire)
