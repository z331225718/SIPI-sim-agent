"""Mutation tests for the archive-only PB-03 Python-oracle evidence."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from verify_pb_03_python_oracle_matrix import (  # noqa: E402
    AGGREGATE,
    REPORT_ONE,
    REPORT_TWO,
    verify,
    verify_pair,
)


class VerifyPb03PythonOracleMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.first = json.loads(REPORT_ONE.read_text(encoding="utf-8"))
        cls.second = json.loads(REPORT_TWO.read_text(encoding="utf-8"))
        cls.aggregate = json.loads(AGGREGATE.read_text(encoding="utf-8"))

    def test_previous_evidence_is_rejected_until_prep_replay_rebind(self) -> None:
        result = verify_pair(self.first, self.second, self.aggregate)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any("source mode mismatch" in error for error in result["errors"]))
        self.assertEqual(self.first["status"], "blocked")
        self.assertTrue(self.first["claims"]["independent_python_payload_oracle"])
        self.assertFalse(self.first["claims"]["global_branch_parity"])

    def test_overlay_source_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.first)
        document["source_mode"] = "git_archive_plus_lane_working_tree_overlay"
        self.assertFalse(verify(document)["valid"])

    def test_self_compare_oracle_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.first)
        case = next(case for case in document["cases"] if case["id"] == "nrz-base")
        case["oracle"]["backend"] = "rust"
        case["oracle"]["source_command"] = "sim-rust"
        self.assertFalse(verify(document)["valid"])

    def test_fixture_and_corpus_binding_mutations_are_rejected(self) -> None:
        document = copy.deepcopy(self.first)
        document["fixture"]["archive_present"] = False
        self.assertFalse(verify(document)["valid"])

        document = copy.deepcopy(self.first)
        document["corpus"]["sha256"] = "0" * 64
        self.assertFalse(verify(document)["valid"])

    def test_global_promotion_mutations_are_rejected(self) -> None:
        document = copy.deepcopy(self.first)
        document["claims"]["global_branch_parity"] = True
        self.assertFalse(verify(document)["valid"])

        document = copy.deepcopy(self.aggregate)
        document["claims"]["global_branch_parity"] = True
        result = verify_pair(self.first, self.second, document)
        self.assertFalse(result["valid"])

    def test_distinct_replay_mutation_is_rejected(self) -> None:
        second = copy.deepcopy(self.second)
        second["run_id"] = self.first["run_id"]
        result = verify_pair(self.first, second, self.aggregate)
        self.assertFalse(result["valid"])

    def test_toolchain_and_build_contract_mutations_are_rejected(self) -> None:
        document = copy.deepcopy(self.first)
        document["toolchain"]["unexpected"] = True
        self.assertFalse(verify(document)["valid"])

        document = copy.deepcopy(self.first)
        document["build"]["unexpected"] = True
        self.assertFalse(verify(document)["valid"])

    def test_aggregate_binary_binding_mutation_is_rejected(self) -> None:
        aggregate = copy.deepcopy(self.aggregate)
        aggregate["builds"] = []
        result = verify_pair(self.first, self.second, aggregate)
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
