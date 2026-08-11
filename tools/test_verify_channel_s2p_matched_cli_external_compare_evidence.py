"""Tests for selected matched-S21 CLI external-evidence verification."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "channel_cli_evidence", ROOT / "tools" / "verify_channel_s2p_matched_cli_external_compare_evidence.py"
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def digest(character: str) -> str:
    return character * 64


class ChannelCliEvidenceTests(unittest.TestCase):
    def evidence(self) -> dict:
        return copy.deepcopy(GATE._load(GATE.EVIDENCE))

    def report(self, evidence: dict) -> dict:
        product = evidence["product"]
        return {
            "schema": GATE.REPORT_SCHEMA,
            "profile_id": GATE.PROFILE_ID,
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
            "non_claims": list(GATE.NON_CLAIMS),
        }

    def test_historical_evidence_rejects_current_cli_source_drift(self) -> None:
        with self.assertRaisesRegex(GATE.EvidenceError, "evidence_product_source_drift"):
            GATE.verify_document(self.evidence())

    def test_rejects_source_cli_and_comparison_drift(self) -> None:
        cases = [
            ("contract", lambda value: value["contract"].update({"sha256": digest("a")})),
            ("core", lambda value: value["core_evidence"].update({"sha256": digest("b")})),
            ("comparator", lambda value: value["comparator"].update({"sha256": digest("c")})),
            ("source", lambda value: value["source"].update({"commit": "0" * 40})),
            ("cli-tree", lambda value: value["product"]["source_trees"].update({"sipi-cli": "0" * 40})),
            ("request", lambda value: value["request"].update({"source_sha256": digest("d")})),
            ("response", lambda value: value["response"].update({"external_profile_acceptance": "accepted"})),
            ("ratio", lambda value: value["comparison"].update({"max_normalized_error_ratio": 1.000001})),
            ("custody", lambda value: value["external_report"].update({"custody": "tracked"})),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                value = self.evidence()
                mutate(value)
                with self.assertRaises(GATE.EvidenceError):
                    GATE.verify_document(value)

    def test_external_report_requires_exact_hash_bound_shape(self) -> None:
        evidence = self.evidence()
        report = self.report(evidence)
        policy = GATE._load(GATE.CONTRACT)
        GATE._validate_report_binding(evidence, report, policy)
        report["response"]["diagnostic_count"] = 1
        with self.assertRaises(GATE.EvidenceError):
            GATE._validate_report_binding(evidence, report, policy)


if __name__ == "__main__":
    unittest.main()
