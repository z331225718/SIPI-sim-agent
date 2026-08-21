"""Mutation tests for the checked-in P5-06 candidate document gate."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_06_pinned_source_external_oracle_candidate_document as gate  # noqa: E402


class CandidateDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate.load_document()

    def test_document_gate_passes_without_external_observer(self) -> None:
        result = gate.validate(self.document)
        self.assertEqual(result["status"], "document_gate_passed_not_acceptance")
        self.assertEqual(result["artifact_hashes_locked"], 7)

    def test_mutation_schema_status_source_and_tool_are_rejected(self) -> None:
        mutations = [
            ("schema", lambda doc: doc.__setitem__("schema", "wrong")),
            ("status", lambda doc: doc.__setitem__("status", "authoritative_verified")),
            ("source", lambda doc: doc["source"].__setitem__("commit", "0" * 40)),
            ("tool", lambda doc: doc["source"]["oracle_tools"][0].__setitem__("git_blob_sha256", "0" * 64)),
        ]
        for name, mutate in mutations:
            candidate = copy.deepcopy(self.document)
            mutate(candidate)
            with self.subTest(name=name):
                with self.assertRaises(gate.DocumentError):
                    gate.validate(candidate)

    def test_mutation_report_artifact_and_nonclaims_are_rejected(self) -> None:
        mutations = [
            ("report", lambda doc: doc["run"]["artifacts"]["comparison_report.json"].__setitem__("sha256", "0" * 64)),
            ("artifact", lambda doc: doc["run"]["artifacts"]["run-01/matlab_oracle.mat"].__setitem__("bytes", 1)),
            ("nonclaims", lambda doc: doc["nonclaims"].pop()),
        ]
        for name, mutate in mutations:
            candidate = copy.deepcopy(self.document)
            mutate(candidate)
            with self.subTest(name=name):
                with self.assertRaises(gate.DocumentError):
                    gate.validate(candidate)

    def test_absolute_local_path_is_rejected_from_checked_in_document(self) -> None:
        candidate = copy.deepcopy(self.document)
        candidate["run"]["logical_root"] = r"C:\external\oracle"
        with self.assertRaisesRegex(gate.DocumentError, "absolute_local_path"):
            gate.validate(candidate)

    def test_gate_does_not_import_dynamic_external_verifier(self) -> None:
        source = (ROOT / "tools" / "verify_p5_06_pinned_source_external_oracle_candidate_document.py").read_text(encoding="utf-8")
        self.assertNotIn("verify_p5_06_authoritative_matlab_oracle_run", source)

    def test_checked_in_audit_has_no_absolute_local_path(self) -> None:
        audit = (ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p5-06-pinned-source-external-matlab-oracle-candidate-run.md").read_text(encoding="utf-8")
        self.assertNotRegex(audit, r"(?im)(?:^|[\s`(])(?:[A-Z]:[\\/]|\\\\|file://)")


if __name__ == "__main__":
    unittest.main()
