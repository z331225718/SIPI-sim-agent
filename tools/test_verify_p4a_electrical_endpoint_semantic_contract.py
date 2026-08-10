"""Tests for the selected P4A electrical endpoint semantic contract."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_endpoint_contract", ROOT / "tools" / "verify_p4a_electrical_endpoint_semantic_contract.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
MANIFEST = ROOT / "docs" / "baselines" / "p4a-electrical-endpoint-semantic-contract.v1.yaml"


class ElectricalEndpointContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_selected_per_leg_topology_remains_unsolved(self) -> None:
        report = GATE.validate_contract(self.document)
        self.assertEqual(report["reference_terminal"], "ref")
        self.assertFalse(report["required"])
        self.assertEqual(report["runtime_status"], "not_supported")

    def test_rejects_implicit_ground_or_differential_substitution(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["terminals"][2]["id"] = "ground"
        with self.assertRaises(GATE.ContractError):
            GATE.validate_contract(altered)
        altered = copy.deepcopy(self.document)
        altered["components"][1]["endpoints"] = ["p", "n"]
        with self.assertRaises(GATE.ContractError):
            GATE.validate_contract(altered)

    def test_rejects_runtime_or_required_promotion(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["profile"]["required"] = True
        with self.assertRaises(GATE.ContractError):
            GATE.validate_contract(altered)
        altered = copy.deepcopy(self.document)
        altered["profile"]["runtime_status"] = "supported"
        with self.assertRaises(GATE.ContractError):
            GATE.validate_contract(altered)


if __name__ == "__main__":
    unittest.main()
