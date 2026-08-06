"""Strict black-box engine adapters for the SIPI control plane."""

from .spi import (
    AdapterContractError,
    BackendAdapter,
    require_backend_request,
    require_backend_result,
    validate_pinned_instance,
    validate_result_identity,
)

__all__ = [
    "AdapterContractError",
    "BackendAdapter",
    "require_backend_request",
    "require_backend_result",
    "validate_pinned_instance",
    "validate_result_identity",
]
