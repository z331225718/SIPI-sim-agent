"""Tests for current-candidate selected matched-S21 CLI evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_channel_s2p_matched_cli_current_external_compare_evidence as GATE
import verify_channel_s2p_matched_cli_current_external_compare_evidence_v2 as GATE_V2
import verify_channel_s2p_matched_cli_current_external_compare_evidence_v3 as GATE_V3
import verify_channel_s2p_matched_cli_current_external_compare_evidence_v4 as GATE_V4
import verify_channel_s2p_matched_cli_current_external_compare_evidence_v5 as GATE_V5
import verify_channel_s2p_matched_cli_current_external_compare_evidence_v6 as GATE_V6
import verify_channel_s2p_matched_cli_current_external_compare_evidence_v7 as GATE_V7
import verify_channel_s2p_matched_cli_current_external_compare_evidence_v8 as GATE_V8
import verify_channel_s2p_matched_cli_current_external_compare_evidence_v9 as GATE_V9
from verify_channel_s2p_matched_external_compare_evidence import EvidenceError as CoreEvidenceError


class ChannelCliCurrentEvidenceTests(unittest.TestCase):
    def evidence(self) -> dict:
        return copy.deepcopy(GATE._load(GATE.EVIDENCE))

    def test_prior_current_evidence_remains_drifted_after_the_cli_changes(self) -> None:
        with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
            GATE.verify_document(self.evidence())

    def test_v2_evidence_remains_drifted_after_receiver_cli_changes(self) -> None:
        with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
            GATE_V2.verify_document(copy.deepcopy(GATE_V2._load(GATE_V2.EVIDENCE)))

    def test_v3_evidence_remains_drifted_after_contract_schema_changes(self) -> None:
        with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
            GATE_V3.verify_document(copy.deepcopy(GATE_V3._load(GATE_V3.EVIDENCE)))

    def test_v4_evidence_remains_drifted_after_the_core_candidate_changes(self) -> None:
        with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
            GATE_V4.verify_document(copy.deepcopy(GATE_V4._load(GATE_V4.EVIDENCE)))

    def test_v5_evidence_remains_drifted_after_the_pwl_cli_route_changes(self) -> None:
        with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
            GATE_V5.verify_document(copy.deepcopy(GATE_V5._load(GATE_V5.EVIDENCE)))

    def test_v6_evidence_remains_drifted_after_sealed_ibis_cli_changes(self) -> None:
        with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
            GATE_V6.verify_document(copy.deepcopy(GATE_V6._load(GATE_V6.EVIDENCE)))

    def test_v7_evidence_remains_drifted_after_sealed_ibis_batch_cli_changes(self) -> None:
        with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
            GATE_V7.verify_document(copy.deepcopy(GATE_V7._load(GATE_V7.EVIDENCE)))

    def test_v8_evidence_remains_drifted_after_the_audit_candidate_changes(self) -> None:
        with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
            GATE_V8.verify_document(copy.deepcopy(GATE_V8._load(GATE_V8.EVIDENCE)))

    def test_v9_evidence_binds_to_current_product_paths(self) -> None:
        result = GATE_V9.verify_document(copy.deepcopy(GATE_V9._load(GATE_V9.EVIDENCE)))
        self.assertTrue(result["valid"])
        self.assertEqual(result["evidence_level"], "hash_only_attestation")

        bad_tree = copy.deepcopy(GATE_V9._load(GATE_V9.EVIDENCE))
        bad_tree["product"]["source_trees"]["sipi-channel"] = "0" * 40
        with self.assertRaises((GATE.EvidenceError, CoreEvidenceError)):
            GATE_V9.verify_document(bad_tree)

    def test_rejects_current_schema_and_source_drift(self) -> None:
        bad_schema = copy.deepcopy(GATE_V4._load(GATE_V4.EVIDENCE))
        bad_schema["schema"] = "sipi.channel.s2p-matched.cli-external-compare-evidence.v1"
        with self.assertRaises((GATE.EvidenceError, CoreEvidenceError)):
            GATE_V4.verify_document(bad_schema)

        bad_tree = copy.deepcopy(GATE_V4._load(GATE_V4.EVIDENCE))
        bad_tree["product"]["source_trees"]["sipi-cli"] = "0" * 40
        with self.assertRaises((GATE.EvidenceError, CoreEvidenceError)):
            GATE_V4.verify_document(bad_tree)

    def test_current_source_drift_rejects_even_an_exact_historical_report(self) -> None:
        evidence = copy.deepcopy(GATE_V3._load(GATE_V3.EVIDENCE))
        product = evidence["product"]
        report = {
            "schema": "sipi.channel.required-profile-cli-compare.v1",
            "profile_id": evidence["profile_id"],
            "status": "passed",
            "accepted": True,
            "policy_sha256": evidence["contract"]["sha256"],
            "source": copy.deepcopy(evidence["source"]),
            "environment": copy.deepcopy(evidence["environment"]),
            "observer": copy.deepcopy(evidence["observer"]),
            "request": copy.deepcopy(evidence["request"]),
            "product": {
                "source_commit": product["source_commit"],
                "source_tree": product["source_tree"],
                "cargo_lock_sha256": product["cargo_lock_sha256"],
                "cargo_version": "cargo test",
                "executable": product["executable"],
                "executable_sha256": product["executable_sha256"],
                "executable_bytes": product["executable_bytes"],
                "cli_kernel_sha256_f64le": product["cli_kernel_sha256_f64le"],
            },
            "response": copy.deepcopy(evidence["response"]),
            "comparison": evidence["comparison"] | {"passed": True},
            "non_claims": copy.deepcopy(GATE.NON_CLAIMS),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            evidence["external_report"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
                GATE_V3.verify_document(evidence, path)

    def test_v9_requires_an_exact_current_candidate_report(self) -> None:
        evidence = copy.deepcopy(GATE_V9._load(GATE_V9.EVIDENCE))
        product = evidence["product"]
        report = {
            "schema": "sipi.channel.required-profile-cli-compare.v1",
            "profile_id": evidence["profile_id"],
            "status": "passed",
            "accepted": True,
            "policy_sha256": evidence["contract"]["sha256"],
            "source": copy.deepcopy(evidence["source"]),
            "environment": copy.deepcopy(evidence["environment"]),
            "observer": copy.deepcopy(evidence["observer"]),
            "request": copy.deepcopy(evidence["request"]),
            "product": {
                "source_commit": product["source_commit"],
                "source_tree": product["source_tree"],
                "cargo_lock_sha256": product["cargo_lock_sha256"],
                "cargo_version": "cargo test",
                "executable": product["executable"],
                "executable_sha256": product["executable_sha256"],
                "executable_bytes": product["executable_bytes"],
                "cli_kernel_sha256_f64le": product["cli_kernel_sha256_f64le"],
            },
            "response": copy.deepcopy(evidence["response"]),
            "comparison": evidence["comparison"] | {"passed": True},
            "non_claims": copy.deepcopy(GATE.NON_CLAIMS),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            evidence["external_report"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertTrue(GATE_V9.verify_document(evidence, path)["report_bound"])
            report["product"]["source_commit"] = "0" * 40
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            evidence["external_report"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises((GATE.EvidenceError, CoreEvidenceError)):
                GATE_V9.verify_document(evidence, path)


if __name__ == "__main__":
    unittest.main()
