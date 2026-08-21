"""Mutation tests for the read-only P7 retirement/release audit."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import verify_p7_retirement_deletion_release_audit as GATE


class RetirementDeletionReleaseAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = copy.deepcopy(GATE._load_document(GATE.EVIDENCE))

    def test_current_audit_is_complete_but_execution_blocked(self) -> None:
        result = GATE.validate(self.document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["path_count"], 24)
        self.assertEqual(result["gate_count"], 37)
        self.assertEqual(result["registry_count"], 2)
        self.assertEqual(result["ready_for_deletion"], 0)

    def test_current_tree_path_digests_are_bound(self) -> None:
        for row in self.document["path_assessments"]:
            self.assertEqual(
                row["tracked_path_set_sha256"],
                GATE.tracked_path_set_sha256(row["path_prefix"]),
            )

    def test_rejects_any_delete_or_gate_removal_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["canonical_sets"]["ready_for_deletion"].append("legacy-test-trees")
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["path_assessments"][0]["ready_for_deletion"] = True
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["drift_gate_audit"]["ready_for_removal"].append("gate-m0_platform_support")
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

    def test_rejects_path_coverage_or_tracked_tree_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["path_assessments"].pop()
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["canonical_sets"]["not_ready_for_deletion"].append("legacy-test-trees")
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["path_assessments"][0]["tracked_path_set_sha256"] = "0" * 64
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["path_assessments"][0]["tracked_file_count"] += 1
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

    def test_rejects_gate_or_release_fact_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["gate_state"]["required_profile_accepted"] = "satisfied"
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["release_gate_facts"]["release_ready"] = True
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["release_gate_facts"]["legal_clearance"] = True
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

    def test_rejects_source_binding_or_registry_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["source_bindings"]["replacement_map"]["sha256"] = "0" * 64
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["external_history_audit"]["promotion_blocked"] = False
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["external_history_audit"]["product_material_status"] = "product_candidate"
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

    def test_rejects_execution_state_mutation_and_nonclaim_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["execution_state"]["path_deletion_performed"] = True
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

        document = copy.deepcopy(self.document)
        document["non_claims"].remove("not_a_path_deletion")
        with self.assertRaises(GATE.AuditError):
            GATE.validate(document)

    def test_verifier_has_no_filesystem_mutation_api(self) -> None:
        source = (ROOT / "tools" / "verify_p7_retirement_deletion_release_audit.py").read_text(encoding="utf-8")
        for token in ("unlink(", "rmdir(", "rmtree(", "shutil.move(", "Path.write_text("):
            self.assertNotIn(token, source)
        self.assertIn('"git", "-C", str(root), "ls-files"', source)


if __name__ == "__main__":
    unittest.main()
