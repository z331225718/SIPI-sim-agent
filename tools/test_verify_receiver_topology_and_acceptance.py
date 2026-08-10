from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("receiver_topology", ROOT / "tools" / "verify_receiver_topology_and_acceptance.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class ReceiverTopologyTests(unittest.TestCase):
    def manifest(self) -> dict:
        return GATE.load(GATE.MANIFEST)

    def acceptance(self) -> dict:
        return GATE.load(GATE.ACCEPTANCE)

    def test_current_contract_has_no_supported_composition(self) -> None:
        report = GATE.verify_document(self.manifest(), self.acceptance())
        self.assertTrue(report["valid"])
        self.assertEqual(report["supported_stage_count"], 0)

    def test_implicit_composition_and_candidate_promotion_fail_closed(self) -> None:
        manifest = self.manifest()
        manifest["composition"] = "implicit"
        with self.assertRaises(GATE.TopologyError):
            GATE.verify_document(manifest, self.acceptance())
        manifest = self.manifest()
        manifest["candidate_profiles"][0]["required"] = True
        with self.assertRaises(GATE.TopologyError):
            GATE.verify_document(manifest, self.acceptance())

    def test_unknown_stage_and_acceptance_drift_fail_closed(self) -> None:
        manifest = self.manifest()
        manifest["stage_kinds"]["mystery"] = copy.deepcopy(manifest["stage_kinds"]["rx_chain"])
        with self.assertRaises(GATE.TopologyError):
            GATE.verify_document(manifest, self.acceptance())
        acceptance = self.acceptance()
        acceptance["profiles"][2]["acceptance"]["required_by"] = "user"
        with self.assertRaises(GATE.TopologyError):
            GATE.verify_document(self.manifest(), acceptance)


if __name__ == "__main__":
    unittest.main()
