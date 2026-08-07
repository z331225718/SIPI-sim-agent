"""Profile reader adapters (M4-07) and cross-profile fixture matrix (M4-08).

Each engine profile consumes a fixture document with pre-extracted
``NetworkTensorV1`` building blocks (axis, ports, data artifact, shape,
encoding, z0, wave definition) and records its profile-specific reader
semantics on the produced tensor.  Native format parsing (Touchstone,
workbook, RFM binaries) is deferred to the domain owners; this slice wires the
profile provenance and guarantees the same semantic input converts into a
valid tensor per profile without claiming numeric equality across engines.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sipi_contracts import NetworkTensorV1, parse_network_tensor


class ReaderError(RuntimeError):
    """Raised when a profile document cannot be read; carries a platform category."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


PROFILES = {
    "com-r480": {"source_reader": "agent-com r4.80 reader", "semantics": "com r4.80 workbook"},
    "com-standard": {"source_reader": "agent-com standard reader", "semantics": "com standard"},
    "pybert-standard": {"source_reader": "PyBERT/scikit-rf reader", "semantics": "s2p standard"},
    "agent-spice-standard": {"source_reader": "agent-spice reader", "semantics": "rfm standard"},
}

REQUIRED_FIELDS = ("axis", "ports", "data", "shape", "complex_encoding", "dtype", "byte_order", "layout", "z0")


def read_network(profile: str, document: Mapping[str, Any]) -> NetworkTensorV1:
    """Convert one profile fixture document into a validated NetworkTensorV1."""
    if profile not in PROFILES:
        raise ReaderError("UnsupportedCapability", f"unknown reader profile: {profile}")
    missing = [field for field in REQUIRED_FIELDS if field not in document]
    if missing:
        raise ReaderError("InvalidRequest", f"profile document missing fields: {missing}")
    wire = {
        "schema": "sipi.network-tensor.v1",
        "parameter_kind": document.get("parameter_kind", "S"),
        "axis": dict(document["axis"]),
        "port_map": {
            "schema": "sipi.port-map.v1",
            "basis": document.get("basis", "single_ended"),
            "index_base": document.get("index_base", 0),
            "ports": [dict(port) for port in document["ports"]],
            "extensions": {},
        },
        "data": dict(document["data"]),
        "shape": dict(document["shape"]),
        "complex_encoding": document["complex_encoding"],
        "dtype": document["dtype"],
        "byte_order": document["byte_order"],
        "layout": document["layout"],
        "z0": dict(document["z0"]),
        "wave_definition": document.get("wave_definition", "pseudo"),
        "reader": {
            "source_reader": PROFILES[profile]["source_reader"],
            "reader_semantics": PROFILES[profile]["semantics"],
            "extensions": {},
        },
        "extensions": {},
    }
    return parse_network_tensor(wire)


def cross_profile_fixture_matrix() -> dict[str, Mapping[str, Any]]:
    """One semantic 2-port S-parameter fixture expressed per reader profile (M4-08)."""
    document = {
        "axis": {
            "schema": "sipi.axis.v1",
            "kind": "frequency",
            "unit": "Hz",
            "dtype": "float64",
            "length": 2,
            "monotonicity": "increasing",
            "uniform": True,
            "sample_location": "bin_center",
            "start": 1.0,
            "step": 1.0,
            "spectrum": {"sidedness": "single", "has_dc": False, "has_nyquist": False},
            "extensions": {},
        },
        "ports": [
            {"id": "p1", "external_index": 0, "kind": "signal", "polarity": 1, "extensions": {}},
            {"id": "p2", "external_index": 1, "kind": "signal", "polarity": -1, "extensions": {}},
        ],
        "data": {
            "schema": "sipi.artifact-ref.v1",
            "content_schema": "sipi.network-matrix.v1",
            "relative_path": "matrix.npy",
            "mime_type": "application/octet-stream",
            "sha256": "b" * 64,
            "byte_length": 128,
            "producer": "fixture",
            "role": "data",
            "extensions": {},
        },
        "shape": {"frequency": 2, "output_ports": 2, "input_ports": 2},
        "complex_encoding": "interleaved",
        "dtype": "complex128",
        "byte_order": "little",
        "layout": "C",
        "z0": {"kind": "scalar", "value": 50.0, "extensions": {}},
    }
    return {profile: dict(document) for profile in PROFILES}
