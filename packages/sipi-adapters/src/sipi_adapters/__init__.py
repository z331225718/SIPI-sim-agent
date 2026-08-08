"""Strict black-box engine adapters for the SIPI control plane."""

from .agent_com import AgentComRunAdapter
from .agent_spice import AgentSpiceHspiceAdapter, AgentSpiceRfmResponseAdapter
from .attestation import AttestationError, WheelAttestation, verify_wheel_bundle
from .capabilities import AdapterCapability, build_engine_capabilities, preflight
from .process import (
    MANAGED_HARD_ENFORCEMENT,
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
from .channel_resolver import CHANNEL_RESPONSE_CONTRACT, ChannelResolutionError, resolve_channel
from .readers import PROFILES, ReaderError, cross_profile_fixture_matrix, read_network
from .venv import BundleExecutionError
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
    "AgentSpiceRfmResponseAdapter",
    "AttestationError",
    "BackendAdapter",
    "BackendOutcome",
    "CHANNEL_RESPONSE_CONTRACT",
    "ChannelResolutionError",
    "BundleExecutionError",
    "build_engine_capabilities",
    "BundleVerificationError",
    "CommandBuilder",
    "ProcessResult",
    "MANAGED_HARD_ENFORCEMENT",
    "PROFILES",
    "PyBertNativeAdapter",
    "ReaderError",
    "UnsupportedCapabilityError",
    "verify_wheel_bundle",
    "cross_profile_fixture_matrix",
    "read_network",
    "resolve_channel",
    "WheelAttestation",
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
