from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import ContractViolation, TransformPolicyV1, parse_transform_policy


def policy(**changes):
    value = {
        "schema": "sipi.transform-policy.v1",
        "reader_semantics": "pybert-standard",
        "transforms": [
            {
                "name": "com-r480.port.reorder",
                "kind": "port",
                "parameters": {"operation": "reorder", "ports": ["p2", "p1", "gnd"]},
                "extensions": {},
            },
            {
                "name": "pybert.interp.linear",
                "kind": "interpolation",
                "parameters": {"method": "linear", "fft_size": 4096, "sample_interval_s": 1.0e-12},
                "extensions": {},
            },
        ],
        "extensions": {},
    }
    value.update(changes)
    return value


class TransformPolicyContractTests(unittest.TestCase):
    def test_policy_parses_and_is_immutable(self):
        raw = policy()
        model = parse_transform_policy(raw)
        self.assertIsInstance(model, TransformPolicyV1)
        raw["transforms"][0]["parameters"]["ports"] = ["p1"]
        self.assertEqual(model.to_wire()["transforms"][0]["parameters"]["ports"], ["p2", "p1", "gnd"])

    def test_implementation_name_requires_namespace(self):
        raw = policy()
        raw["transforms"][0]["name"] = "reorder"
        with self.assertRaises(ContractViolation):
            parse_transform_policy(raw)

    def test_numeric_transform_kinds_single_step(self):
        raw = policy()
        raw["transforms"].append(
            {
                "name": "pybert.interp.nearest",
                "kind": "interpolation",
                "parameters": {"method": "nearest"},
                "extensions": {},
            }
        )
        with self.assertRaisesRegex(ContractViolation, "duplicate_transform"):
            parse_transform_policy(raw)

    def test_port_transform_requires_explicit_operation_and_ports(self):
        raw = policy()
        raw["transforms"][0]["parameters"] = {"ports": ["p1"]}
        with self.assertRaisesRegex(ContractViolation, "explicit operation"):
            parse_transform_policy(raw)
        raw = policy()
        raw["transforms"][0]["parameters"] = {"operation": "polarity"}
        with self.assertRaisesRegex(ContractViolation, "affected ports"):
            parse_transform_policy(raw)
        raw = policy()
        raw["transforms"][0]["parameters"] = {"operation": "identity"}
        model = parse_transform_policy(raw)
        self.assertEqual(model.to_wire()["transforms"][0]["kind"], "port")

    def test_public_parameter_bounds(self):
        raw = policy()
        raw["transforms"].append(
            {"name": "pybert.passivity.enforce", "kind": "passivity", "parameters": {"method": "enforce", "tolerance": -1.0}, "extensions": {}}
        )
        with self.assertRaises(ContractViolation):
            parse_transform_policy(raw)
        raw = policy()
        raw["transforms"][1]["parameters"] = {"method": "linear", "fft_size": 1}
        with self.assertRaises(ContractViolation):
            parse_transform_policy(raw)
        raw = policy()
        raw["transforms"][1]["parameters"] = {"method": "linear", "sample_interval_s": 0.0}
        with self.assertRaises(ContractViolation):
            parse_transform_policy(raw)

    def test_boolean_flags_strict(self):
        raw = policy()
        raw["transforms"].append(
            {"name": "pybert.dc.constant", "kind": "dc", "parameters": {"method": "constant", "extrapolate": "yes"}, "extensions": {}}
        )
        with self.assertRaises(ContractViolation):
            parse_transform_policy(raw)
        raw = policy()
        raw["transforms"].append(
            {"name": "pybert.causal.time-shift", "kind": "causality", "parameters": {"method": "time_shift", "enforce": 1}, "extensions": {}}
        )
        with self.assertRaises(ContractViolation):
            parse_transform_policy(raw)

    def test_implementation_private_parameters_tolerated(self):
        raw = policy()
        raw["transforms"][1]["parameters"]["window"] = "hann"
        raw["transforms"][1]["parameters"]["zero_pad_factor"] = 4
        model = parse_transform_policy(raw)
        self.assertEqual(model.to_wire()["transforms"][1]["parameters"]["window"], "hann")

    def test_unknown_kind_and_fields_rejected(self):
        raw = policy()
        raw["transforms"][0]["kind"] = "fft"
        with self.assertRaises(ContractViolation):
            parse_transform_policy(raw)
        raw = policy()
        raw["implicit_default"] = True
        with self.assertRaises(ContractViolation):
            parse_transform_policy(raw)

    def test_single_chain_covers_all_five_kinds(self):
        raw = policy()
        raw["transforms"] = [
            {"name": "pybert.port.identity", "kind": "port", "parameters": {"operation": "identity"}, "extensions": {}},
            {"name": "pybert.interp.none", "kind": "interpolation", "parameters": {"method": "none"}, "extensions": {}},
            {"name": "pybert.dc.none", "kind": "dc", "parameters": {"method": "none"}, "extensions": {}},
            {"name": "pybert.causal.none", "kind": "causality", "parameters": {"method": "none"}, "extensions": {}},
            {"name": "pybert.passivity.none", "kind": "passivity", "parameters": {"method": "none", "tolerance": 0.0}, "extensions": {}},
        ]
        model = parse_transform_policy(raw)
        self.assertEqual([item["kind"] for item in model.to_wire()["transforms"]], ["port", "interpolation", "dc", "causality", "passivity"])


if __name__ == "__main__":
    unittest.main()
