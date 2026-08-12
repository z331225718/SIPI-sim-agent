"""Negative tests for the v2-contract external ADS oracle reference."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_ads_reference", ROOT / "tools/verify_p3c_external_ads_prbs9_reference.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class ExternalAdsReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-external-ads-prbs9-reference.v1.yaml").read_text(encoding="utf-8"))

    def test_current_reference_is_external_only_and_not_accepted(self) -> None:
        report = GATE.verify_document(self.document)
        self.assertTrue(report["external_ads_runtime_observed"])
        self.assertTrue(report["external_reference_observed"])
        self.assertFalse(report["candidate_acceptance_evaluated"])
        self.assertFalse(report["release_promoted"])

    def test_edge_and_admission_promotion_drift_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["source_edge"]["rise_time_seconds"] = 0.0
        with self.assertRaisesRegex(GATE.ReferenceError, "source_edge_invalid"):
            GATE.verify_document(document, hashes=set())
        document = copy.deepcopy(self.document)
        document["admission"]["release_ledger_promoted"] = True
        with self.assertRaisesRegex(GATE.ReferenceError, "admission_gate_drift"):
            GATE.verify_document(document, hashes=set())

    def test_external_hash_leak_and_historical_attempt_drift_are_rejected(self) -> None:
        with self.assertRaisesRegex(GATE.ReferenceError, "external_custody_leak"):
            GATE.verify_document(self.document, hashes={GATE.REPORT_SHA256})
        original = GATE.sha256_file

        def historical_drift(path: Path) -> str:
            if path.name == GATE.ATTEMPT.name:
                return "0" * 64
            return original(path)

        with mock.patch.object(GATE, "sha256_file", side_effect=historical_drift):
            with self.assertRaisesRegex(GATE.ReferenceError, "historical_attempt_source_drift"):
                GATE.verify_gates(ROOT)

    def test_clean_archive_and_cross_file_gate_drift_are_rejected(self) -> None:
        tree = subprocess.CompletedProcess([], 0, stdout=f"{GATE.ARCHIVE_TREE}\n", stderr="")
        with mock.patch.object(GATE.subprocess, "run", return_value=tree):
            with mock.patch.object(GATE, "archive_runner_bytes", return_value=b"unexpected"):
                with self.assertRaisesRegex(GATE.ReferenceError, "clean_archive_runner_drift"):
                    GATE.verify_clean_archive(ROOT)
        original = GATE.load_yaml

        def p4b_drift(path: Path):
            if path.name == GATE.P4B.name:
                return {"status": "admitted"}
            return original(path)

        with mock.patch.object(GATE, "load_yaml", side_effect=p4b_drift):
            with self.assertRaisesRegex(GATE.ReferenceError, "p4b_runtime_admission_drift"):
                GATE.verify_gates(ROOT)
        with mock.patch.object(GATE.json, "loads", return_value={"rows": [{"id": "compare", "acceptance_state": "accepted", "blockers": []}]}):
            with self.assertRaisesRegex(GATE.ReferenceError, "release_compare_metric_gate_drift"):
                GATE.verify_gates(ROOT)


if __name__ == "__main__":
    unittest.main()
