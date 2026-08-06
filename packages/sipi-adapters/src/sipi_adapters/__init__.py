"""Strict black-box engine adapters for the SIPI control plane."""

from .agent_com import AgentComRunAdapter
from .agent_spice import AgentSpiceHspiceAdapter
from .capabilities import AdapterCapability, build_engine_capabilities, preflight
from .process import (
    BackendOutcome,
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
from .pybert import PyBertNativeAdapter
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
    "AdapterCapability",
    "AgentComRunAdapter",
    "AgentSpiceHspiceAdapter",
    "BackendAdapter",
    "BackendOutcome",
    "build_engine_capabilities",
    "BundleVerificationError",
    "CommandBuilder",
    "ProcessResult",
    "PyBertNativeAdapter",
    "UnsupportedCapabilityError",
    "assemble_backend_result",
    "execute_backend",
    "filtered_env",
    "invocation",
    "materialize_bound_inputs",
    "platform_error",
    "preflight",
    "require_backend_request",
    "require_backend_result",
    "run_process",
    "validate_pinned_instance",
    "validate_result_identity",
    "verify_engine_bundle",
]
