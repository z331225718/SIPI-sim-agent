"""Mutation tests for the v5 fixed TRAN current evidence binding."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "current_tran_evidence_v5",
    ROOT / "tools" / "verify_tran_rc_pulse_current_external_compare_evidence_v5.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class CurrentTranEvidenceV5Tests(unittest.TestCase):
    def document(self) -> dict[str, object]:
        return copy.deepcopy(GATE._load(GATE.EVIDENCE))

    def test_v5_hash_only_record_is_valid(self) -> None:
        result = GATE.verify_document(self.document())
        self.assertEqual(
            result,
            {
                "schema": GATE.SCHEMA,
                "valid": True,
                "profile_id": "tran-rc-pulse-v1",
                "report_bound": False,
                "evidence_level": "hash_only_attestation",
            },
        )

    def test_v5_cli_reports_current_record_as_valid(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", "tools/verify_tran_rc_pulse_current_external_compare_evidence_v5.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(json.loads(completed.stdout), {
            "evidence_level": "hash_only_attestation",
            "profile_id": "tran-rc-pulse-v1",
            "report_bound": False,
            "schema": GATE.SCHEMA,
            "valid": True,
        })

    def test_rejects_historical_schema_and_product_commit_drift(self) -> None:
        wrong_schema = self.document()
        wrong_schema["schema"] = GATE.HISTORICAL_SCHEMA
        with self.assertRaises(GATE.EvidenceError):
            GATE.verify_document(wrong_schema)
        drift = self.document()
        drift["product"]["source_commit"] = "0" * 40
        with self.assertRaisesRegex(GATE.EvidenceError, "current_evidence_product_commit_invalid"):
            GATE.verify_document(drift)

    def test_rejects_product_tree_and_lock_drift(self) -> None:
        for field, value in (
            ("source_trees", {"sipi-tran": "0" * 40}),
            ("cargo_lock_blob", "0" * 40),
        ):
            with self.subTest(field=field):
                drift = self.document()
                if field == "source_trees":
                    drift["product"][field].update(value)
                else:
                    drift["product"][field] = value
                with self.assertRaisesRegex(GATE.EvidenceError, "evidence_product_source_drift"):
                    GATE.verify_document(drift)

    def test_rejects_tolerance_and_custody_mutations(self) -> None:
        widened = self.document()
        widened["comparison"]["voltage_out_volts"]["relative_tolerance"] = 1.0
        with self.assertRaisesRegex(GATE.EvidenceError, "evidence_comparison_contract_mismatch"):
            GATE.verify_document(widened)
        custody = self.document()
        custody["external_report"]["custody"] = "tracked"
        with self.assertRaises(GATE.EvidenceError):
            GATE.verify_document(custody)


if __name__ == "__main__":
    unittest.main()
