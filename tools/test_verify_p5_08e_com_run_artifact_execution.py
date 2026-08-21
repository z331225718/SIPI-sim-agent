"""Mutation tests for the P5-08e artifact execution verifier."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import verify_p5_08e_com_run_artifact_execution as GATE


class P508eVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.CHARTER)

    def _mutated_charter(self, document: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / GATE.CHARTER.name
        path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def test_current_contract_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["semantics"], "product_owned_bounded_execution_complete")
        self.assertEqual(result["behavioral_replication"], "not_claimed")
        self.assertFalse(result["legacy_wire_changed"])

    def test_rejects_source_hash_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["implementation"]["sha256"] = "0" * 64
        with patch.object(GATE, "CHARTER", self._mutated_charter(document)):
            with self.assertRaisesRegex(GATE.P508eError, "source_hash_drift"):
                GATE.validate()

    def test_rejects_binding_metadata_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["bindings"][0]["sha256"] = "0" * 64
        with patch.object(GATE, "CHARTER", self._mutated_charter(document)):
            with self.assertRaisesRegex(GATE.P508eError, "binding_metadata_drift"):
                GATE.validate()

    def test_rejects_report_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["report"]["product_acceptance"] = True
        with patch.object(GATE, "CHARTER", self._mutated_charter(document)):
            with self.assertRaisesRegex(GATE.P508eError, "report_scope_invalid"):
                GATE.validate()

    def test_rejects_audit_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / GATE.AUDIT.name
            mutated.write_bytes(GATE.AUDIT.read_bytes() + b"\nmutation\n")
            with patch.object(GATE, "AUDIT", mutated):
                with self.assertRaisesRegex(GATE.P508eError, "audit_binding_invalid"):
                    GATE.validate()

    def test_rejects_legacy_p5_08d_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / GATE.LEGACY_ARTIFACT_SOURCE.name
            mutated.write_bytes(GATE.LEGACY_ARTIFACT_SOURCE.read_bytes() + b"\n")
            with patch.object(GATE, "LEGACY_ARTIFACT_SOURCE", mutated):
                with self.assertRaisesRegex(GATE.P508eError, "legacy_p5_08d_source_drift"):
                    GATE.validate()


if __name__ == "__main__":
    unittest.main()
