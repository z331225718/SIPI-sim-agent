"""Strict backend adapter boundary.

Adapters are strict-only: they consume exactly one
``BackendExecutionRequestV1`` and return one ``BackendExecutionResultV1``.
Run envelopes, backend selection, fallback and comparison are owned by the
runtime and must never cross this boundary.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sipi_contracts import BackendExecutionRequestV1, BackendExecutionResultV1

BACKEND_REQUEST_SCHEMA = "sipi.backend-execution-request.v1"
BACKEND_RESULT_SCHEMA = "sipi.backend-execution-result.v1"
_IDENTITY_FIELDS = (
    "run_id",
    "analysis_id",
    "attempt_id",
    "backend_execution_id",
    "role",
    "engine_instance_id",
    "bundle_hash",
    "operation",
    "payload_schema",
)


class AdapterContractError(TypeError):
    """Raised when an envelope crosses the strict adapter boundary illegally."""


class UnsupportedCapabilityError(AdapterContractError):
    """Raised when a request asks for a capability the adapter cannot provide."""


@runtime_checkable
class BackendAdapter(Protocol):
    """One strict engine execution per call; no selection or aggregation."""

    def execute(self, request: BackendExecutionRequestV1) -> BackendExecutionResultV1:
        """Run one backend execution and return its single result."""
        ...


def require_backend_request(value: object) -> BackendExecutionRequestV1:
    if not isinstance(value, BackendExecutionRequestV1):
        raise AdapterContractError(
            f"adapter input must be a BackendExecutionRequestV1, got {type(value).__name__}"
        )
    return value


def require_backend_result(value: object) -> BackendExecutionResultV1:
    if not isinstance(value, BackendExecutionResultV1):
        raise AdapterContractError(
            f"adapter output must be a BackendExecutionResultV1, got {type(value).__name__}"
        )
    return value


def validate_pinned_instance(request: BackendExecutionRequestV1, instance_id: str) -> None:
    if request["engine_instance_id"] != instance_id:
        raise AdapterContractError(
            f"request engine_instance_id {request['engine_instance_id']!r} "
            f"does not match the pinned engine instance {instance_id!r}"
        )


def validate_result_identity(
    request: BackendExecutionRequestV1,
    result: BackendExecutionResultV1,
) -> None:
    for field in _IDENTITY_FIELDS:
        if request[field] != result[field]:
            raise AdapterContractError(f"result {field} does not match the request")
