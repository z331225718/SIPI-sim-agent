"""Mutation tests for the P4B-02 production adapter selection."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import verify_p4b_02_production_parameter_adapter_selection as GATE


class ProductionAdapterSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.EVIDENCE)

    def _path(self, document: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / GATE.EVIDENCE.name
        path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def test_current_selection_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["adapter"], "bounded_typed_host_forwarded_subset")
        self.assertEqual(result["selected_semantic_helper_count"], 0)
        self.assertEqual(result["quarantine_count"], 34)
        self.assertEqual(result["delete_candidate_count"], 159)
        self.assertFalse(result["bulk_deletion_performed"])

    def test_rejects_typed_helper_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["production_adapter"]["selected_semantic_helper_modules"] = ["parameter_value_v1"]
        with patch.object(GATE, "EVIDENCE", self._path(document)):
            with self.assertRaisesRegex(GATE.AdapterSelectionError, "semantic_helper_selection_not_empty"):
                GATE.validate()

    def test_rejects_worker_hash_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["production_adapter"]["worker"]["sha256"] = "0" * 64
        with patch.object(GATE, "EVIDENCE", self._path(document)):
            with self.assertRaisesRegex(GATE.AdapterSelectionError, "worker_binding_invalid"):
                GATE.validate()

    def test_rejects_typed_adapter_hash_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["production_adapter"]["typed_adapter"]["sha256"] = "0" * 64
        with patch.object(GATE, "EVIDENCE", self._path(document)):
            with self.assertRaisesRegex(GATE.AdapterSelectionError, "typed_adapter_binding_invalid"):
                GATE.validate()

    def test_rejects_inventory_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["inventory"]["keep_for_product"] = 1
        with patch.object(GATE, "EVIDENCE", self._path(document)):
            with self.assertRaisesRegex(GATE.AdapterSelectionError, "inventory_invalid"):
                GATE.validate()

    def test_rejects_bulk_deletion_claim(self) -> None:
        document = copy.deepcopy(self.document)
        document["deletion_plan"]["bulk_deletion_performed"] = True
        with patch.object(GATE, "EVIDENCE", self._path(document)):
            with self.assertRaisesRegex(GATE.AdapterSelectionError, "deletion_plan_invalid"):
                GATE.validate()

    def test_rejects_audit_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory) / GATE.AUDIT.name
            audit.write_bytes(GATE.AUDIT.read_bytes() + b"\nmutation\n")
            with patch.object(GATE, "AUDIT", audit):
                with self.assertRaisesRegex(GATE.AdapterSelectionError, "audit_binding_invalid"):
                    GATE.validate()


if __name__ == "__main__":
    unittest.main()
