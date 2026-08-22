"""Mutation tests for immutable COM-01 replay evidence."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

import yaml


sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_com_01_direct_replay_bound import DEFAULT_MANIFEST, VerificationError, verify


class Com01BoundReplayVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(DEFAULT_MANIFEST.read_text(encoding="utf-8"))

    def verify_mutation(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify(path)

    def test_baseline_is_valid(self):
        result = verify()
        self.assertEqual(result["formal_replays"], 2)
        self.assertEqual(result["fingerprint_drift_count"], 1)

    def test_candidate_commit_mutation_fails(self):
        self.verify_mutation(lambda value: value["candidate"].update(commit="0" * 40))

    def test_candidate_archive_mutation_fails(self):
        self.verify_mutation(lambda value: value["candidate"].update(archive_sha256="0" * 64))

    def test_preflight_claim_mutation_fails(self):
        self.verify_mutation(
            lambda value: value["candidate"].update(preallocation_preflight_retained=False)
        )

    def test_report_digest_mutation_fails(self):
        self.verify_mutation(
            lambda value: value["formal_replays"]["invocations"][0].update(sha256="0" * 64)
        )

    def test_duplicate_nonce_mutation_fails(self):
        self.verify_mutation(
            lambda value: value["formal_replays"]["invocations"][1].update(
                fresh_run_nonce=value["formal_replays"]["invocations"][0]["fresh_run_nonce"]
            )
        )

    def test_outcome_promotion_mutation_fails(self):
        self.verify_mutation(
            lambda value: value["formal_replays"].update(
                expected_outcomes={"passed": 14}
            )
        )

    def test_status_promotion_mutation_fails(self):
        self.verify_mutation(lambda value: value.update(status="complete_com_parity"))

    def test_binary_reproducibility_overclaim_fails(self):
        self.verify_mutation(
            lambda value: value["formal_replays"].update(binary_bit_reproducible=True)
        )

    def test_runner_hash_mutation_fails(self):
        self.verify_mutation(
            lambda value: value["harness"].update(replay_runner_sha256="0" * 64)
        )

    def test_audit_hash_mutation_fails(self):
        self.verify_mutation(lambda value: value["audit"].update(sha256="0" * 64))

    def test_non_claim_removal_fails(self):
        self.verify_mutation(lambda value: value["non_claims"].pop())


if __name__ == "__main__":
    unittest.main()
