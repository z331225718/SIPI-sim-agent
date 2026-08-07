from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import CHANNEL_RESPONSE_CONTRACT, ChannelResolutionError, resolve_channel
from sipi_contracts import parse_channel_resolution_policy, parse_network_tensor


def network():
    return {
        "schema": "sipi.network-tensor.v1",
        "parameter_kind": "S",
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
        "port_map": {
            "schema": "sipi.port-map.v1",
            "basis": "single_ended",
            "index_base": 0,
            "ports": [
                {"id": "p1", "external_index": 0, "kind": "signal", "polarity": 1, "extensions": {}},
                {"id": "p2", "external_index": 1, "kind": "signal", "polarity": -1, "extensions": {}},
            ],
            "extensions": {},
        },
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
        "wave_definition": "pseudo",
        "reader": {"source_reader": "scikit-rf", "reader_semantics": "s2p", "extensions": {}},
        "extensions": {},
    }


def policy(**changes):
    value = {
        "schema": "sipi.channel-resolution-policy.v1",
        "reader_semantics": "scikit-rf s2p",
        "port_selection": [
            {"port_id": "p1", "role": "signal", "extensions": {}},
            {"port_id": "p2", "role": "signal", "extensions": {}},
        ],
        "termination": "match",
        "interpolation": {"kind": "none", "extensions": {}},
        "dc": {"method": "none", "extensions": {}},
        "causality": {"method": "none", "extensions": {}},
        "ifft": {"extensions": {}},
        "normalization": {"fft": "none", "extensions": {}},
        "output": {"signal_intent": "voltage", "current_to_voltage_sign": 1, "extensions": {}},
        "extensions": {},
    }
    value.update(changes)
    return value


class ChannelResolverTests(unittest.TestCase):
    def test_contract_pin(self):
        self.assertEqual(CHANNEL_RESPONSE_CONTRACT["symbol"], "ChannelResponseV1")
        self.assertIn("impulseResponseVoltsPerSecond", CHANNEL_RESPONSE_CONTRACT["fields"])

    def test_identity_resolution_builds_channel_and_report(self):
        channel, report = resolve_channel(
            parse_network_tensor(network()),
            parse_channel_resolution_policy(policy()),
            impulse_response_volts_per_second=[0.0, 1.0, 0.5],
            source_impedance=50.0,
            load_impedance=50.0,
            sample_interval_s=1.0e-12,
        )
        self.assertEqual(channel["sampleInterval"], 1.0e-12)
        self.assertEqual(channel["impulseResponseVoltsPerSecond"], [0.0, 1.0, 0.5])
        expected_hash = hashlib.sha256(json.dumps(channel, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(report.to_wire()["output_hash"], expected_hash)
        kinds = [item["kind"] for item in report.to_wire()["transforms"]]
        self.assertEqual(kinds, ["port_selection", "termination", "interpolation", "dc", "causality", "ifft", "normalization"])

    def test_unsupported_transforms_fail_closed(self):
        with self.assertRaises(ChannelResolutionError):
            resolve_channel(
                parse_network_tensor(network()),
                parse_channel_resolution_policy(policy(dc={"method": "constant", "extensions": {}})),
                impulse_response_volts_per_second=[0.0, 1.0],
                source_impedance=50.0,
                load_impedance=50.0,
                sample_interval_s=1.0e-12,
            )
        with self.assertRaises(ChannelResolutionError):
            resolve_channel(
                parse_network_tensor(network()),
                parse_channel_resolution_policy(policy(interpolation={"kind": "linear", "fft_size": 64, "sample_interval_s": 1.0e-12, "extensions": {}})),
                impulse_response_volts_per_second=[0.0, 1.0],
                source_impedance=50.0,
                load_impedance=50.0,
                sample_interval_s=1.0e-12,
            )

    def test_missing_impulse_rejected(self):
        with self.assertRaises(ChannelResolutionError):
            resolve_channel(
                parse_network_tensor(network()),
                parse_channel_resolution_policy(policy()),
                impulse_response_volts_per_second=[],
                source_impedance=50.0,
                load_impedance=50.0,
                sample_interval_s=1.0e-12,
            )


if __name__ == "__main__":
    unittest.main()
