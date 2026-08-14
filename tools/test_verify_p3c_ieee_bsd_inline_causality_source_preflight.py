"""Mutation tests for IEEE BSD inline-causality source preflight."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

from verify_p3c_ieee_bsd_inline_causality_source_preflight import PreflightError, verify_document


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-inline-causality-source-preflight.v1.yaml"


class InlineCausalityPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))

    def rejects(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(PreflightError):
            verify_document(document)

    def test_baseline_is_valid(self) -> None:
        self.assertTrue(verify_document(self.document)["valid"])

    def test_helper_admission_or_source_drift_rejects(self) -> None:
        self.rejects(lambda value: value["dependency_boundary"]["blocked_materials"].clear())
        self.rejects(lambda value: value["source"].__setitem__("git_blob", "0" * 40))

    def test_implementation_or_causal_promotion_rejects(self) -> None:
        self.rejects(lambda value: value["gates"].__setitem__("causality_enforcement_implemented", True))
        self.rejects(lambda value: value["gates"].__setitem__("causal_impulse_admitted", True))

    def test_unbounded_or_truncation_scope_rejects(self) -> None:
        self.rejects(lambda value: value["inline_causality_loop"]["excluded_from_this_loop"].remove("impulse_response_truncation_threshold"))
        self.rejects(lambda value: value["blockers"].remove("inline_causality_policy_values_and_failure_semantics_not_owner_confirmed"))


if __name__ == "__main__":
    unittest.main()
