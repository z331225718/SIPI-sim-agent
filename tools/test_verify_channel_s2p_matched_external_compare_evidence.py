"""Tests for selected matched-S21 external-evidence verification."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_channel_s2p_matched_external_compare_evidence as GATE
import verify_channel_s2p_matched_external_compare_evidence_v2 as GATE_V2


def digest(character: str) -> str:
    return character * 64


class ChannelEvidenceTests(unittest.TestCase):
    def evidence(self) -> dict:
        return copy.deepcopy(GATE._load(GATE_V2.EVIDENCE))

    def report(self, evidence: dict) -> dict:
        return {
            "schema": GATE.REPORT_SCHEMA,
            "profile_id": GATE.PROFILE_ID,
            "status": "passed",
            "accepted": True,
            "policy_sha256": evidence["contract"]["sha256"],
            "source": evidence["source"],
            "environment": {"platform": "windows-x86_64", "environment_hash": evidence["observer"]["environment_hash"]},
            "observer": {
                "implementation": evidence["observer"]["implementation"],
                "fresh_run_kernel_sha256_f64le": evidence["observer"]["kernel_sha256_f64le"],
                "fft_length": evidence["observer"]["fft_length"],
                "sample_interval_seconds": evidence["observer"]["sample_interval_seconds"],
            },
            "product_input": evidence["product"]["product_input"],
            "product": {
                "cargo_lock_sha256": evidence["product"]["cargo_lock_sha256"],
                "cargo_version": "cargo test",
                "fft_length": evidence["product"]["fft_length"],
                "kernel_sha256_f64le": evidence["product"]["kernel_sha256_f64le"],
                "runner": "sipi-channel-kernel-runner",
                "runner_bytes": evidence["product"]["runner_bytes"],
                "runner_sha256": evidence["product"]["runner_sha256"],
                "sample_interval_seconds": evidence["product"]["sample_interval_seconds"],
                "source_commit": evidence["product"]["source_commit"],
                "source_tree": evidence["product"]["source_tree"],
            },
            "comparison": evidence["comparison"] | {"passed": True},
            "non_claims": list(GATE.REPORT_NON_CLAIMS),
        }

    def test_prior_evidence_remains_drifted_and_v2_binds_to_current_product_inputs(self) -> None:
        with self.assertRaisesRegex(GATE.EvidenceError, "evidence_product_source_drift"):
            GATE.verify_document(copy.deepcopy(GATE._load(GATE.EVIDENCE)))
        result = GATE_V2.verify_document(self.evidence())
        self.assertTrue(result["valid"])

    def test_rejects_policy_source_product_and_metric_drift(self) -> None:
        cases = [
            ("policy", lambda value: value["contract"].update({"sha256": digest("a")})),
            ("comparator", lambda value: value["comparator"].update({"sha256": digest("b")})),
            ("source", lambda value: value["source"].update({"commit": "0" * 40})),
            ("observer_runs", lambda value: value["observer"].update({"fresh_runs": 1})),
            ("product_tree", lambda value: value["product"]["source_trees"].update({"sipi-channel": "0" * 40})),
            ("lock", lambda value: value["product"].update({"cargo_lock_blob": "0" * 40})),
            ("outside_policy", lambda value: value["comparison"].update({"max_absolute_error": 2.0e-9})),
            ("all_sample_ratio", lambda value: value["comparison"].update({"max_normalized_error_ratio": 1.000001})),
            ("report_custody", lambda value: value["external_report"].update({"custody": "tracked"})),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                value = self.evidence()
                mutate(value)
                with self.assertRaises(GATE.EvidenceError):
                    GATE_V2.verify_document(value)

    def test_external_report_is_hash_bound_and_exact(self) -> None:
        evidence = self.evidence()
        report = self.report(evidence)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            evidence["external_report"]["sha256"] = GATE._sha256_file(path)
            historical_shape = copy.deepcopy(evidence)
            historical_shape["schema"] = GATE.SCHEMA
            bound = GATE.verify_document(historical_shape, path)
            self.assertTrue(bound["report_bound"])
            self.assertEqual(bound["evidence_level"], "fresh_report_bound")
            report["comparison"]["passed"] = False
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            evidence["external_report"]["sha256"] = GATE._sha256_file(path)
            historical_shape = copy.deepcopy(evidence)
            historical_shape["schema"] = GATE.SCHEMA
            with self.assertRaisesRegex(GATE.EvidenceError, "external_report_"):
                GATE.verify_document(historical_shape, path)
            report = self.report(evidence)
            report["non_claims"][0] = "promoted"
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            evidence["external_report"]["sha256"] = GATE._sha256_file(path)
            historical_shape = copy.deepcopy(evidence)
            historical_shape["schema"] = GATE.SCHEMA
            with self.assertRaisesRegex(GATE.EvidenceError, "external_report_"):
                GATE.verify_document(historical_shape, path)


if __name__ == "__main__":
    unittest.main()
