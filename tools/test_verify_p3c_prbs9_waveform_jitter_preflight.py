"""Negative tests for the PRBS9 waveform/jitter preflight boundary."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_prbs9_preflight", ROOT / "tools/verify_p3c_prbs9_waveform_jitter_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class Prbs9WaveformJitterPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-preflight.v1.yaml").read_text(encoding="utf-8"))

    def verify(self, document: dict) -> dict:
        return GATE.verify_document(document)

    def test_current_policy_is_only_a_preflight(self) -> None:
        report = self.verify(self.document)
        self.assertFalse(report["acceptance_ready"])
        self.assertFalse(report["runtime_invoked"])
        self.assertFalse(report["release_ledger_promoted"])

    def test_prbs_and_waveform_semantic_drift_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["prbs"]["polynomial"] = "x9+x4+1"
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["prbs"]["samples_per_ui"] = 16
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["waveform"]["alignment"] = "correlation_allowed"
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["waveform"]["relative_rms_error_limit"] = 0.02
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)

    def test_pending_fields_and_admission_cannot_be_promoted(self) -> None:
        document = copy.deepcopy(self.document)
        document["prbs"]["seed"] = 1
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["jitter"]["acceptance_ready"] = True
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["admission"]["ami_runtime_invoked"] = True
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)

    def test_p4b_gate_drift_is_rejected(self) -> None:
        with mock.patch.object(GATE, "load_yaml", return_value={"status": "admitted"}):
            with self.assertRaisesRegex(GATE.PreflightError, "p4b_runtime_admission_drift"):
                self.verify(self.document)

    def test_release_compare_gate_drift_is_rejected(self) -> None:
        invalid_rows = [{"id": "compare", "acceptance_state": "accepted", "blockers": ["metric_profile_semantics_not_implemented"]}]
        with mock.patch.object(GATE.json, "loads", return_value={"rows": invalid_rows}):
            with self.assertRaisesRegex(GATE.PreflightError, "release_compare_metric_gate_drift"):
                self.verify(self.document)
        invalid_rows = [{"id": "compare", "acceptance_state": "specified", "blockers": ["other"]}]
        with mock.patch.object(GATE.json, "loads", return_value={"rows": invalid_rows}):
            with self.assertRaisesRegex(GATE.PreflightError, "release_compare_metric_gate_drift"):
                self.verify(self.document)


if __name__ == "__main__":
    unittest.main()
