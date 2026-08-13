"""Mutation tests for the external selected-S4P impulse diagnostic evidence."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_impulse_diagnostic_evidence", ROOT / "tools" / "verify_p3c_selected_s4p_impulse_causality_diagnostic_evidence.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class SelectedS4pImpulseDiagnosticEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-selected-s4p-impulse-causality-diagnostic-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_exact_external_observation_remains_non_admission(self) -> None:
        report = GATE.verify_document(self.document)
        self.assertEqual(report["fresh_custody_runs"], 2)
        self.assertFalse(report["causal_impulse_admitted"])
        self.assertFalse(report["release_admitted"])

    def test_metric_threshold_repair_and_promotion_mutations_fail_closed(self) -> None:
        for mutate in (
            lambda value: value["external_observation"].__setitem__("negative_energy_fraction_bits", "0000000000000000"),
            lambda value: value["observed_interpretation"].__setitem__("threshold_selected", True),
            lambda value: value["observed_interpretation"].__setitem__("causal_impulse_admitted", True),
            lambda value: value["observed_interpretation"].__setitem__("causal_repair_or_delay_shift_applied", True),
            lambda value: value["blockers"].remove("direct_port_implementation_scope_missing"),
        ):
            altered = copy.deepcopy(self.document)
            mutate(altered)
            with self.assertRaises(GATE.EvidenceError):
                GATE.verify_document(altered)

    def test_rejects_custody_or_release_relaxation(self) -> None:
        for mutate in (
            lambda value: value["external_observation"].__setitem__("report_path_retained", True),
            lambda value: value["external_observation"]["manifest_sha256s"].__setitem__(1, value["external_observation"]["manifest_sha256s"][0]),
            lambda value: value["non_claims"].pop(),
            lambda value: value.__setitem__("status", "accepted"),
        ):
            altered = copy.deepcopy(self.document)
            mutate(altered)
            with self.assertRaises(GATE.EvidenceError):
                GATE.verify_document(altered)


if __name__ == "__main__":
    unittest.main()
