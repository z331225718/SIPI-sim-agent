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
from verify_channel_s2p_matched_external_compare_evidence import EvidenceError as CoreEvidenceError


class ChannelCliCurrentEvidenceTests(unittest.TestCase):
    def evidence(self) -> dict:
        return copy.deepcopy(GATE._load(GATE.EVIDENCE))

    def test_prior_current_evidence_remains_drifted_after_the_cli_changes(self) -> None:
        with self.assertRaisesRegex((GATE.EvidenceError, CoreEvidenceError), "evidence_product_source_drift"):
            GATE.verify_document(self.evidence())

    def test_v2_evidence_binds_to_current_product_paths(self) -> None:
        result = GATE_V2.verify_document(copy.deepcopy(GATE_V2._load(GATE_V2.EVIDENCE)))
        self.assertTrue(result["valid"])
        self.assertEqual(result["evidence_level"], "hash_only_attestation")

    def test_rejects_current_schema_and_source_drift(self) -> None:
        bad_schema = copy.deepcopy(GATE_V2._load(GATE_V2.EVIDENCE))
        bad_schema["schema"] = "sipi.channel.s2p-matched.cli-external-compare-evidence.v1"
        with self.assertRaises((GATE.EvidenceError, CoreEvidenceError)):
            GATE_V2.verify_document(bad_schema)

        bad_tree = copy.deepcopy(GATE_V2._load(GATE_V2.EVIDENCE))
        bad_tree["product"]["source_trees"]["sipi-cli"] = "0" * 40
        with self.assertRaises((GATE.EvidenceError, CoreEvidenceError)):
            GATE_V2.verify_document(bad_tree)

    def test_requires_an_exact_current_candidate_report(self) -> None:
        evidence = copy.deepcopy(GATE_V2._load(GATE_V2.EVIDENCE))
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
            self.assertTrue(GATE_V2.verify_document(evidence, path)["report_bound"])
            report["product"]["source_commit"] = "0" * 40
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            evidence["external_report"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises((GATE.EvidenceError, CoreEvidenceError)):
                GATE_V2.verify_document(evidence, path)


if __name__ == "__main__":
    unittest.main()
