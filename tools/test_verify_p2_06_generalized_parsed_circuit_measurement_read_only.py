"""Mutation tests for the P2-06 read-only parsed-circuit/measurement audit."""

from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p2_06_generalized_parsed_circuit_measurement_read_only as gate


class P206ReadOnlyAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.RECORD)

    def test_record_and_git_objects_are_bound(self) -> None:
        result = gate.verify()
        self.assertTrue(result["valid"])
        self.assertEqual(result["implementation"], "none")
        self.assertEqual(result["publication"], "blocked")
        self.assertFalse(result["external_source_verified"])

    def test_external_objects_are_optional_and_explicit(self) -> None:
        external_root = os.environ.get("SIPI_AGENT_SPICE_ROOT")
        if not external_root:
            self.skipTest("SIPI_AGENT_SPICE_ROOT is not set")
        result = gate.verify(Path(external_root))
        self.assertTrue(result["valid"])
        self.assertTrue(result["external_source_verified"])

    def test_parser_or_measurement_admission_mutations_fail_closed(self) -> None:
        mutations = (
            ("parser", lambda value: value["current_product"]["contract_observation"].__setitem__("parsed_circuit", "covered")),
            ("measurement", lambda value: value["current_product"]["contract_observation"].__setitem__("measurement_semantics", "implemented")),
            ("result", lambda value: value["slice_decision"].__setitem__("selected", "measurement_result")),
        )
        for reason, mutation in mutations:
            with self.subTest(reason=reason):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaises(gate.EvidenceError):
                    gate.verify_document(value)

    def test_object_and_license_mutations_fail_closed(self) -> None:
        mutations = (
            ("product", lambda value: value["current_product"]["source_inventory"].__setitem__("crates/sipi-tran/src/lib.rs", "0" * 40)),
            ("external", lambda value: value["external_agent_spice"]["source_inventory"].__setitem__("native/agent-spice-sim/src/netlist.rs", "0" * 40)),
            ("license", lambda value: value["external_agent_spice"]["license_boundary"].__setitem__("crate_declared_license", "GPL-3.0")),
        )
        for reason, mutation in mutations:
            with self.subTest(reason=reason):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaises(gate.EvidenceError):
                    gate.verify_document(value)

    def test_owner_input_and_non_claim_guards_remain_required(self) -> None:
        value = copy.deepcopy(self.document)
        value["slice_decision"]["owner_decisions_required_before_any_future_slice"] = []
        with self.assertRaisesRegex(gate.EvidenceError, "owner_inputs_invalid"):
            gate.verify_document(value)

        value = copy.deepcopy(self.document)
        value["non_claims"] = [True]
        with self.assertRaisesRegex(gate.EvidenceError, "non_claims_invalid"):
            gate.verify_document(value)


if __name__ == "__main__":
    unittest.main()
