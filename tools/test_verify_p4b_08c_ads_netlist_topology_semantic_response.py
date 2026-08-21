from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_08c_ads_netlist_topology_semantic_response as GATE


class AdsTopologySemanticResponseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE.load_yaml(GATE.EVIDENCE)

    def test_current_observation_is_valid_without_external_paths(self) -> None:
        result = GATE.verify_document(self.document)
        self.assertEqual(result, {"valid": True, "dynamic_checked": False})

    def test_fixed_snp_port_reorder_cannot_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["topology"]["blocks"][1]["port_order"] = [1, 2, 3, 4]
        with self.assertRaises(GATE.TopologyObservationError):
            GATE.verify_document(document)

    def test_fixed_node_map_cannot_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["topology"]["blocks"][0]["port_map"]["3"] = "N__7"
        with self.assertRaises(GATE.TopologyObservationError):
            GATE.verify_document(document)

    def test_low_frequency_observation_cannot_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["semantic_response"]["low_frequency_observation"]["sdd21_db"] += 0.001
        with self.assertRaises(GATE.TopologyObservationError):
            GATE.verify_document(document)

    def test_product_admission_cannot_be_mutated(self) -> None:
        document = copy.deepcopy(self.document)
        document["admission"]["typed_edge_to_channel"] = True
        with self.assertRaises(GATE.TopologyObservationError):
            GATE.verify_document(document)

    def test_dynamic_verifier_requires_absolute_external_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GATE.TopologyObservationError):
                GATE.verify_external_inputs(self.document, Path(temporary))

    def test_dynamic_mode_rejects_partial_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GATE.TopologyObservationError):
                GATE.validate(ROOT, ads_root=Path(temporary).resolve())

    def test_dynamic_mode_requires_generated_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GATE.TopologyObservationError):
                GATE.validate(ROOT, ads_root=Path(temporary).resolve(), pybert_root=Path(temporary).resolve())

    def test_generated_artifact_hash_cannot_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["semantic_response"]["generated_artifacts_external_only"]["network"]["sha256"] = "0" * 64
        with self.assertRaises(GATE.TopologyObservationError):
            GATE.verify_document(document)

    def test_missing_generated_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GATE.TopologyObservationError):
                GATE.verify_generated_outputs(self.document, Path(temporary).resolve())


if __name__ == "__main__":
    unittest.main()
