from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import (
    ChannelResolutionPolicyV1,
    ChannelResolutionReportV1,
    ContractViolation,
    parse_channel_resolution_policy,
    parse_channel_resolution_report,
)


def policy(**changes):
    value = {
        "schema": "sipi.channel-resolution-policy.v1",
        "reader_semantics": "scikit-rf s2p",
        "port_selection": [
            {"port_id": "p1", "role": "signal", "extensions": {}},
            {"port_id": "p2", "role": "signal", "extensions": {}},
            {"port_id": "gnd", "role": "reference", "extensions": {}},
        ],
        "termination": "match",
        "interpolation": {"kind": "linear", "fft_size": 4096, "sample_interval_s": 1.0e-12, "extensions": {}},
        "dc": {"method": "constant", "extrapolate": True, "extensions": {}},
        "causality": {"method": "time_shift", "enforce": True, "extensions": {}},
        "ifft": {"window": "hann", "zero_pad_factor": 4, "trim": {"leading_samples": 16, "trailing_samples": 16}, "extensions": {}},
        "normalization": {"fft": "amplitude", "scaling": "1", "extensions": {}},
        "output": {"signal_intent": "voltage", "current_to_voltage_sign": 1, "reference_port": "gnd", "extensions": {}},
        "extensions": {},
    }
    value.update(changes)
    return value


def report(**changes):
    value = {
        "schema": "sipi.channel-resolution-report.v1",
        "producer": "channel-resolver",
        "source_network_hash": "a" * 64,
        "policy_hash": "b" * 64,
        "output_hash": "c" * 64,
        "transforms": [
            {"kind": "port_selection", "applied": True, "details": {"selected": ["p1", "p2"]}},
            {"kind": "ifft", "applied": True, "details": {"fft_size": 4096}},
        ],
        "warnings": [],
        "extensions": {},
    }
    value.update(changes)
    return value


class ChannelResolutionContractTests(unittest.TestCase):
    def test_policy_parses_and_is_immutable(self):
        raw = policy()
        model = parse_channel_resolution_policy(raw)
        self.assertIsInstance(model, ChannelResolutionPolicyV1)
        raw["termination"] = "open"
        self.assertEqual(model.to_wire()["termination"], "match")

    def test_policy_port_and_output_rules(self):
        duplicate = policy()
        duplicate["port_selection"][1]["port_id"] = "p1"
        with self.assertRaisesRegex(ContractViolation, "unique"):
            parse_channel_resolution_policy(duplicate)
        raw = policy()
        del raw["output"]["current_to_voltage_sign"]
        with self.assertRaisesRegex(ContractViolation, "current_to_voltage_sign"):
            parse_channel_resolution_policy(raw)
        raw = policy()
        raw["output"]["reference_port"] = "missing"
        with self.assertRaisesRegex(ContractViolation, "selected port"):
            parse_channel_resolution_policy(raw)

    def test_report_parses_tolerantly(self):
        model = parse_channel_resolution_report(report())
        self.assertIsInstance(model, ChannelResolutionReportV1)
        raw = report()
        raw["future_optional"] = {"kept": True}
        model = parse_channel_resolution_report(raw)
        self.assertEqual(model.extra["future_optional"], {"kept": True})

    def test_report_transform_kinds_unique_and_hash_format(self):
        duplicate = report()
        duplicate["transforms"].append({"kind": "port_selection", "applied": False})
        with self.assertRaisesRegex(ContractViolation, "unique"):
            parse_channel_resolution_report(duplicate)
        bad_hash = report(output_hash="not-hex")
        with self.assertRaises(ContractViolation):
            parse_channel_resolution_report(bad_hash)


if __name__ == "__main__":
    unittest.main()
