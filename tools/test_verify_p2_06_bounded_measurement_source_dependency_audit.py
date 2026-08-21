"""Mutation tests for the P2-06 bounded-measurement dependency audit."""

from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p2_06_bounded_measurement_source_dependency_audit as gate


class P206BoundedMeasurementAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.RECORD)

    def test_document_only_is_valid_without_external_sibling(self) -> None:
        result = gate.verify()
        self.assertTrue(result["valid"])
        self.assertEqual(result["implementation"], "none")
        self.assertFalse(result["external_source_verified"])

    def test_external_verification_is_explicit_and_optional(self) -> None:
        root = os.environ.get("SIPI_AGENT_SPICE_ROOT")
        if not root:
            self.skipTest("SIPI_AGENT_SPICE_ROOT is not set")
        result = gate.verify(Path(root))
        self.assertTrue(result["valid"])
        self.assertTrue(result["external_source_verified"])

    def test_contract_and_candidate_mutations_fail_closed(self) -> None:
        mutations = (
            ("measurement", lambda value: value["product_baseline"]["current_contract"].__setitem__("measurement_semantics", "implemented")),
            ("candidate", lambda value: value["candidate_slice"].__setitem__("disposition", "accepted")),
            ("window", lambda value: value["candidate_slice"]["proposed_restriction"].__setitem__("window", "interpolated")),
            ("dependency", lambda value: value["pinned_original_project"]["direct_dependencies_from_manifest"].append("new-crate")),
            ("source_graph", lambda value: value["pinned_original_project"]["parser_measurement_graph"]["measurement_evaluation"].append("simulator.rs:999 invented")),
        )
        for reason, mutation in mutations:
            with self.subTest(reason=reason):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaises(gate.EvidenceError):
                    gate.verify_document(value)

    def test_object_and_missing_semantics_mutations_fail_closed(self) -> None:
        mutations = (
            ("product_object", lambda value: value["product_baseline"]["source_inventory"].__setitem__("crates/sipi-tran/src/lib.rs", "0" * 40)),
            ("external_object", lambda value: value["pinned_original_project"]["source_inventory"].__setitem__("native/agent-spice-sim/src/netlist.rs", "0" * 40)),
            ("owner_input", lambda value: value["minimum_missing_semantics"]["required_owner_inputs"].clear()),
        )
        for reason, mutation in mutations:
            with self.subTest(reason=reason):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaises(gate.EvidenceError):
                    gate.verify_document(value)


if __name__ == "__main__":
    unittest.main()
