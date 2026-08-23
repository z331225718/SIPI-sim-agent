"""Mutation tests for the AS-02..AS-06 evidence contract."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import aggregate_as_remaining as aggregate  # noqa: E402
import verify_as_remaining_direct_port as verifier  # noqa: E402


EVIDENCE = {
    "AS-02": ROOT / "docs/baselines/as-02-fit-sparam-cascade-direct-port.v1.yaml",
    "AS-03": ROOT / "docs/baselines/as-03-fit-yparam-direct-port.v1.yaml",
    "AS-04": ROOT / "docs/baselines/as-04-tune-yparam-tran-direct-port.v1.yaml",
    "AS-05": ROOT / "docs/baselines/as-05-run-hspice-rust-control-direct-port.v1.yaml",
    "AS-06": ROOT / "docs/baselines/as-06-run-rfm-direct-port.v1.yaml",
}


class VerifyAsRemainingDirectPortTests(unittest.TestCase):
    def test_pinned_documents_are_valid(self):
        for row, path in EVIDENCE.items():
            with self.subTest(row=row):
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
                result = verifier.verify(document, evidence_path=path)
                self.assertTrue(result["valid"], result["blockers"])

    def _assert_mutation_blocked(self, row, mutate):
        path = EVIDENCE[row]
        document = copy.deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
        mutate(document)
        result = verifier.verify(document, evidence_path=path)
        self.assertFalse(result["valid"])
        self.assertTrue(result["blockers"])

    def test_source_commit_mutation_is_blocked(self):
        for row in EVIDENCE:
            with self.subTest(row=row):
                self._assert_mutation_blocked(row, lambda doc: doc["source"].__setitem__("commit", "0" * 40))

    def test_status_overclaim_is_blocked(self):
        for row in EVIDENCE:
            with self.subTest(row=row):
                self._assert_mutation_blocked(row, lambda doc: doc.__setitem__("status", "rust_parity_accepted"))

    def test_replay_contract_mutation_is_blocked(self):
        for row in EVIDENCE:
            with self.subTest(row=row):
                self._assert_mutation_blocked(row, lambda doc: doc["oracle_replay"].__setitem__("replay_count", 1))

    def test_v1_bound_replay_claim_is_blocked(self):
        for row in EVIDENCE:
            with self.subTest(row=row):
                def bind_v1(doc):
                    doc["oracle_replay"].update(
                        binding_status="content_addressed_v2",
                        content_addressed=True,
                        immutable_source_binding=True,
                    )

                self._assert_mutation_blocked(row, bind_v1)

    def test_audit_hash_mutation_is_blocked(self):
        for row in EVIDENCE:
            with self.subTest(row=row):
                self._assert_mutation_blocked(row, lambda doc: doc["audit"].__setitem__("sha256", "0" * 64))

    def test_unsupported_semantics_cannot_be_removed(self):
        for row in EVIDENCE:
            with self.subTest(row=row):
                self._assert_mutation_blocked(row, lambda doc: doc["direct_port"].__setitem__("unsupported_semantics", []))

    def test_evidence_tool_inventory_is_required(self):
        for row in EVIDENCE:
            with self.subTest(row=row):
                self._assert_mutation_blocked(row, lambda doc: doc["evidence"].__setitem__("aggregate", "tools/missing-aggregate.py"))

    def test_aggregate_requires_every_pinned_case_in_both_replays(self):
        def report(instance, case="case"):
            return {
                "schema": "sipi.agent-spice-as-02-replay.v1",
                "workflow": "AS-02",
                "upstream": {"commit": aggregate.COMMIT, "tree": aggregate.TREE},
                "corpus": [case],
                "corpus_expected": True,
                "replay_instance_sha256": instance,
                "binding_status": "unbound_preparation_observation",
                "content_addressed_replay": False,
                "immutable_source_binding": False,
                "runs": [
                    {"tree_sha256": "b" * 64, "returncode": 0, "cases": [{"case": case, "expected_result": True}]},
                    {"tree_sha256": "b" * 64, "returncode": 0, "cases": [{"case": case, "expected_result": True}]},
                ],
            }

        result = aggregate.aggregate("AS-02", [report("a" * 64), report("c" * 64)])
        self.assertFalse(result["content_addressed_replay"])
        with self.assertRaises(ValueError):
            aggregate.aggregate("AS-02", [report("a" * 64), report("c" * 64, case="wrong")])


if __name__ == "__main__":
    unittest.main()
