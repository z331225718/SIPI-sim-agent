"""Strict black-box engine adapters for the SIPI control plane."""

from .agent_spice import AgentSpiceHspiceAdapter
from .process import (
    BundleVerificationError,
    CommandBuilder,
    ProcessResult,
    assemble_backend_result,
    execute_backend,
    filtered_env,
    invocation,
    materialize_bound_inputs,
    platform_error,
    run_process,
    verify_engine_bundle,
)
from .spi import (
    AdapterContractError,
    BackendAdapter,
    UnsupportedCapabilityError,
    require_backend_request,
    require_backend_result,
    validate_pinned_instance,
    validate_result_identity,
)

__all__ = [
    "AdapterContractError",
    "AgentSpiceHspiceAdapter",
    "BackendAdapter",
    "BundleVerificationError",
    "CommandBuilder",
    "ProcessResult",
    "UnsupportedCapabilityError",
    "assemble_backend_result",
    "execute_backend",
    "filtered_env",
    "invocation",
    "materialize_bound_inputs",
    "platform_error",
    "require_backend_request",
    "require_backend_result",
    "run_process",
    "validate_pinned_instance",
    "validate_result_identity",
    "verify_engine_bundle",
]
