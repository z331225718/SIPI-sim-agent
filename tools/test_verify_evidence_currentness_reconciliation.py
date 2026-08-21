from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_evidence_currentness_reconciliation as gate


class EvidenceCurrentnessReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        value = yaml.safe_load(gate.DEFAULT.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise AssertionError("baseline must be a mapping")
        cls.document = value

    def test_document_is_valid(self) -> None:
        result = gate.verify_document(copy.deepcopy(self.document))
        self.assertTrue(result["valid"])
        self.assertEqual(result["record_count"], 26)

    def test_runtime_matches_recorded_truth_table(self) -> None:
        gate.verify_runtime(copy.deepcopy(self.document))

    def test_mutations_fail_closed(self) -> None:
        mutations = (
            lambda d: d["policy"].__setitem__("historical_evidence_immutable", False),
            lambda d: d["reconciliation"].__setitem__("new_current_successors", ["invented"]),
            lambda d: d["truth_table"][0].__setitem__("evidence_sha256", "0" * 64),
            lambda d: d["truth_table"][0].__setitem__("classification", "current"),
            lambda d: d["truth_table"][0].__setitem__("release_claim", True),
            lambda d: d["truth_table"][0].__setitem__("evidence", "../PLAN.md"),
            lambda d: d["truth_table"].append(copy.deepcopy(d["truth_table"][0])),
            lambda d: d["truth_table"][0]["expected"].__setitem__("stderr_contains", "relaxed"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = copy.deepcopy(self.document)
                mutate(document)
                with self.assertRaises(gate.ReconciliationError):
                    gate.verify_document(document)


if __name__ == "__main__":
    unittest.main()
