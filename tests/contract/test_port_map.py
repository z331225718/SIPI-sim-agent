from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import ContractViolation, PortMapV1, parse_port_map


def port_map(**changes):
    value = {
        "schema": "sipi.port-map.v1",
        "basis": "single_ended",
        "index_base": 0,
        "ports": [
            {"id": "p1", "external_index": 0, "kind": "signal", "polarity": 1, "extensions": {}},
            {"id": "p2", "external_index": 1, "kind": "signal", "polarity": -1, "extensions": {}},
            {"id": "gnd", "external_index": 2, "kind": "reference", "polarity": 1, "extensions": {}},
        ],
        "extensions": {},
    }
    value.update(changes)
    return value


def mixed_map(**changes):
    value = {
        "schema": "sipi.port-map.v1",
        "basis": "mixed_mode",
        "index_base": 1,
        "ports": [
            {"id": "p1p", "external_index": 1, "kind": "signal", "polarity": 1, "pair_with": "p1n", "extensions": {}},
            {"id": "p1n", "external_index": 2, "kind": "signal", "polarity": -1, "pair_with": "p1p", "extensions": {}},
            {"id": "cm", "external_index": 3, "kind": "common_mode", "polarity": 1, "extensions": {}},
        ],
        "extensions": {},
    }
    value.update(changes)
    return value


class PortMapContractTests(unittest.TestCase):
    def test_single_ended_parses_and_is_immutable(self):
        raw = port_map()
        model = parse_port_map(raw)
        self.assertIsInstance(model, PortMapV1)
        raw["ports"][0]["external_index"] = 9
        self.assertEqual(model.to_wire()["ports"][0]["external_index"], 0)

    def test_duplicate_ids_and_indexes_rejected(self):
        with self.assertRaisesRegex(ContractViolation, "unique"):
            parse_port_map(port_map(ports=[port_map()["ports"][0], port_map()["ports"][0]]))
        duplicate_index = port_map()
        duplicate_index["ports"][1]["external_index"] = duplicate_index["ports"][0]["external_index"]
        with self.assertRaisesRegex(ContractViolation, "duplicate_index"):
            parse_port_map(duplicate_index)

    def test_reference_must_be_declared_and_not_self(self):
        good = port_map()
        good["ports"][0]["reference"] = "gnd"
        parse_port_map(good)
        with self.assertRaisesRegex(ContractViolation, "undeclared"):
            parse_port_map(port_map(ports=[{**port_map()["ports"][0], "reference": "missing"}] + port_map()["ports"][1:]))
        with self.assertRaisesRegex(ContractViolation, "itself"):
            parse_port_map(port_map(ports=[{**port_map()["ports"][0], "reference": "p1"}] + port_map()["ports"][1:]))

    def test_pairing_rules(self):
        parse_port_map(mixed_map())
        with self.assertRaisesRegex(ContractViolation, "mixed_mode"):
            parse_port_map(port_map(ports=[{**port_map()["ports"][0], "pair_with": "p2"}] + port_map()["ports"][1:]))
        asymmetric = mixed_map()
        asymmetric["ports"][1]["pair_with"] = "cm"
        with self.assertRaisesRegex(ContractViolation, "asymmetric_pair"):
            parse_port_map(asymmetric)
        self_pair = mixed_map()
        self_pair["ports"][0]["pair_with"] = "p1p"
        with self.assertRaisesRegex(ContractViolation, "itself"):
            parse_port_map(self_pair)
        unknown = mixed_map()
        unknown["ports"][0]["pair_with"] = "missing"
        with self.assertRaisesRegex(ContractViolation, "undeclared"):
            parse_port_map(unknown)
        common_with_pair = mixed_map()
        common_with_pair["ports"][2]["pair_with"] = "p1p"
        with self.assertRaisesRegex(ContractViolation, "only signal"):
            parse_port_map(common_with_pair)


if __name__ == "__main__":
    unittest.main()
