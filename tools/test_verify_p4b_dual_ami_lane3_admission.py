"""Mutation tests for the P4B dual-AMI Lane 3 admission verifier."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import verify_p4b_dual_ami_lane3_admission as gate


class Lane3AdmissionVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate.load_document()

    def test_current_blocker_record_passes(self) -> None:
        result = gate.verify_document(self.document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["rights"], "blocked")
        self.assertFalse(result["runtime_invoked"])

    def test_rejects_owner_permission_as_vendor_rights(self) -> None:
        changed = copy.deepcopy(self.document)
        changed[gate.STAGES[0]]["runtime_rights"]["owner_permission_is_vendor_rights"] = True
        with self.assertRaisesRegex(gate.Lane3AdmissionError, "rights_boundary_invalid"):
            gate.verify_document(changed)

    def test_rejects_unobserved_parameter_promotion(self) -> None:
        changed = copy.deepcopy(self.document)
        changed[gate.STAGES[1]]["selected_parameter_names"] = ["unobserved"]
        with self.assertRaisesRegex(gate.Lane3AdmissionError, "parameter_names_must_remain_empty"):
            gate.verify_document(changed)

    def test_rejects_dll_consumption_claim_from_declaration(self) -> None:
        changed = copy.deepcopy(self.document)
        changed[gate.STAGES[1]]["existing_ads_log_set"]["proves_dll_internal_consumption"] = True
        with self.assertRaisesRegex(gate.Lane3AdmissionError, "dll_consumption_claim"):
            gate.verify_document(changed)

    def test_rejects_static_imports_as_dynamic_closure(self) -> None:
        changed = copy.deepcopy(self.document)
        changed[gate.STAGES[2]]["dynamic_dependency_closure"] = "ready"
        with self.assertRaisesRegex(gate.Lane3AdmissionError, "dynamic_closure_claim"):
            gate.verify_document(changed)

    def test_rejects_worker_admission_without_security_boundary(self) -> None:
        changed = copy.deepcopy(self.document)
        changed[gate.STAGES[3]]["vendor_worker_admitted"] = True
        with self.assertRaisesRegex(gate.Lane3AdmissionError, "worker_admission_claim"):
            gate.verify_document(changed)

    def test_rejects_runtime_invocation_after_failed_prior_gate(self) -> None:
        changed = copy.deepcopy(self.document)
        changed[gate.STAGES[4]]["dll_loaded"] = True
        with self.assertRaisesRegex(gate.Lane3AdmissionError, "runtime_noninvocation_invalid"):
            gate.verify_document(changed)

    def test_rejects_stage_reordering(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["serial_stage_order"][0], changed["serial_stage_order"][1] = (
            changed["serial_stage_order"][1],
            changed["serial_stage_order"][0],
        )
        with self.assertRaisesRegex(gate.Lane3AdmissionError, "serial_stage_order_invalid"):
            gate.verify_document(changed)

    def test_external_check_rejects_missing_asset_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(gate.Lane3AdmissionError, "external_asset_missing"):
                gate.verify_external_assets(self.document, Path(directory).resolve())


if __name__ == "__main__":
    unittest.main()
