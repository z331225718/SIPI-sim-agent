"""Unique production channel resolver (M4-05b).

``resolve_channel`` turns a validated ``NetworkTensorV1`` plus a
``ChannelResolutionPolicyV1`` into a PyBERT ``ChannelResponseV1`` wire document
and a ``sipi.channel-resolution-report.v1`` record.  Numeric transforms
(interpolation, DC extrapolation, causality enforcement, FFT-window IFFT,
non-trivial normalization) are intentionally fail-closed until the domain
owner implements them; this slice pins the external contract and the
provenance/audit record.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sipi_contracts import ChannelResolutionPolicyV1, ChannelResolutionReportV1, NetworkTensorV1, parse_channel_resolution_report


class ChannelResolutionError(RuntimeError):
    """Raised when a resolution cannot be produced; carries a platform category."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


# External contract pin: PyBERT native/pybert-core/src/input.rs, symbol ChannelResponseV1.
CHANNEL_RESPONSE_CONTRACT = {
    "source": "py-bert-agent",
    "path": "native/pybert-core/src/input.rs",
    "symbol": "ChannelResponseV1",
    "fields": ["sampleInterval", "impulseResponseVoltsPerSecond", "sourceImpedance", "loadImpedance"],
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def resolve_channel(
    network: NetworkTensorV1,
    policy: ChannelResolutionPolicyV1,
    *,
    impulse_response_volts_per_second: list[float],
    source_impedance: float,
    load_impedance: float,
    sample_interval_s: float,
) -> tuple[dict[str, Any], ChannelResolutionReportV1]:
    """Resolve a network into a ChannelResponseV1 wire document plus audit report."""
    network_wire = network.to_wire()
    policy_wire = policy.to_wire()
    transforms: list[dict[str, Any]] = []
    warnings: list[str] = []

    if network_wire["parameter_kind"] not in {"S", "Z"}:
        raise ChannelResolutionError("UnsupportedCapability", f"resolver supports S/Z networks, got {network_wire['parameter_kind']}")

    transforms.append(
        {
            "kind": "port_selection",
            "applied": True,
            "details": {"selected": [item["port_id"] for item in policy_wire["port_selection"]]},
        }
    )
    transforms.append({"kind": "termination", "applied": True, "details": {"termination": policy_wire["termination"]}})

    interpolation = policy_wire["interpolation"]
    if interpolation["kind"] != "none":
        raise ChannelResolutionError("UnsupportedCapability", f"numeric interpolation {interpolation['kind']} is not implemented; fail-closed")
    transforms.append({"kind": "interpolation", "applied": False, "details": {"kind": "none"}})

    if policy_wire["dc"]["method"] != "none":
        raise ChannelResolutionError("UnsupportedCapability", f"dc {policy_wire['dc']['method']} is not implemented; fail-closed")
    transforms.append({"kind": "dc", "applied": False, "details": {"method": "none"}})

    if policy_wire["causality"]["method"] != "none":
        raise ChannelResolutionError("UnsupportedCapability", f"causality {policy_wire['causality']['method']} is not implemented; fail-closed")
    transforms.append({"kind": "causality", "applied": False, "details": {"method": "none"}})

    ifft = policy_wire["ifft"]
    if ifft.get("window") is not None or ifft.get("zero_pad_factor") is not None:
        raise ChannelResolutionError("UnsupportedCapability", "numeric IFFT window/zero-pad is not implemented; fail-closed")
    transforms.append({"kind": "ifft", "applied": False, "details": {"trim": ifft.get("trim", {})}})

    normalization = policy_wire["normalization"]
    if normalization["fft"] not in {"none", "amplitude"}:
        raise ChannelResolutionError("UnsupportedCapability", f"normalization {normalization['fft']} is not implemented; fail-closed")
    if normalization["fft"] != "none":
        warnings.append("amplitude normalization is declared but not applied by this resolver slice")
    transforms.append({"kind": "normalization", "applied": normalization["fft"] == "none", "details": {"fft": normalization["fft"]}})

    if not impulse_response_volts_per_second or any(not isinstance(value, (int, float)) for value in impulse_response_volts_per_second):
        raise ChannelResolutionError("InvalidRequest", "impulse response is required and must be numeric")

    sign = policy_wire["output"].get("current_to_voltage_sign", 1)
    channel = {
        "sampleInterval": float(sample_interval_s),
        "impulseResponseVoltsPerSecond": [float(value) * sign for value in impulse_response_volts_per_second],
        "sourceImpedance": float(source_impedance),
        "loadImpedance": float(load_impedance),
    }
    report = parse_channel_resolution_report(
        {
            "schema": "sipi.channel-resolution-report.v1",
            "producer": "sipi-adapters.channel_resolver",
            "source_network_hash": _sha256_bytes(_canonical_json(network_wire)),
            "policy_hash": _sha256_bytes(_canonical_json(policy_wire)),
            "output_hash": _sha256_bytes(_canonical_json(channel)),
            "transforms": transforms,
            "warnings": warnings,
            "extensions": {},
        }
    )
    return channel, report
