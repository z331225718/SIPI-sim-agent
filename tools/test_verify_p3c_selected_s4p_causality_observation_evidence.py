"""Mutation tests for selected-S4P causality observation evidence."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

from verify_p3c_selected_s4p_causality_observation_evidence import VerificationError, verify_document


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/baselines/p3c-selected-s4p-causality-observation-evidence.v1.yaml"


class CausalityObservationEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))

    def rejects(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(VerificationError):
            verify_document(document)

    def test_baseline_is_valid(self) -> None:
        self.assertTrue(verify_document(self.document)["valid"])

    def test_repeatability_or_digest_mutation_rejects(self) -> None:
        self.rejects(lambda value: value["external_observation"].__setitem__("fresh_custody_runs", 1))
        self.rejects(lambda value: value["external_observation"]["outcome"].__setitem__("causal_response_sha256", "0" * 64))

    def test_causal_impulse_or_release_promotion_rejects(self) -> None:
        self.rejects(lambda value: value["admission"].__setitem__("causal_impulse_admitted", True))
        self.rejects(lambda value: value["admission"].__setitem__("release_ledger_promoted", True))

    def test_nonclaim_or_blocker_relaxation_rejects(self) -> None:
        self.rejects(lambda value: value.__setitem__("non_claims", []))
        self.rejects(lambda value: value.__setitem__("blockers", []))


if __name__ == "__main__":
    unittest.main()
