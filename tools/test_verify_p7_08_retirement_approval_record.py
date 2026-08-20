"""Tests for the signed P7-08 retirement approval record."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p7_08_retirement_approval_record as GATE


class ApprovalRecordTests(unittest.TestCase):
    def test_record_is_owner_approved(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertTrue(result["approved"])

    def test_approval_is_signed(self) -> None:
        record = GATE.load_yaml(GATE.RECORD)
        self.assertEqual(record["approval_state"], "owner_approved")
        self.assertTrue(isinstance(record["approved_by"], str) and record["approved_by"].strip())
        self.assertIsNotNone(GATE.APPROVED_AT_RE.match(record["approved_at_utc"]))

    def test_evidence_bindings_exact(self) -> None:
        record = GATE.load_yaml(GATE.RECORD)
        bindings = record["evidence_bindings"]
        self.assertEqual(bindings["replacement_map"]["sha256"], GATE.sha256_file(ROOT / GATE.MAP))
        self.assertEqual(bindings["drift_gate_strategy"]["sha256"], GATE.sha256_file(ROOT / GATE.STRATEGY))

    def test_gates_other_than_approval_still_pending(self) -> None:
        record = GATE.load_yaml(GATE.RECORD)
        gates = record["effective_gates"]
        self.assertEqual(gates["owner_retirement_approval"], "filled_by_this_record")
        self.assertEqual(gates["required_profile_accepted"], "still_pending")
        self.assertEqual(gates["same_batch_drift_gate_removal"], "still_pending")
        self.assertEqual(gates["release_license_fresh_machine_gates"], "still_pending")

    def test_rejects_unsigned_template_record(self) -> None:
        # Reverting the record to its template state must fail closed.
        record = GATE.load_yaml(GATE.RECORD)
        record["approval_state"] = "pending_owner_signature"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "record.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "RECORD", tmp_path):
                with self.assertRaises(GATE.ApprovalRecordError):
                    GATE.validate(ROOT)

    def test_rejects_blank_signer(self) -> None:
        record = GATE.load_yaml(GATE.RECORD)
        record["approved_by"] = "   "
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "record.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "RECORD", tmp_path):
                with self.assertRaises(GATE.ApprovalRecordError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
