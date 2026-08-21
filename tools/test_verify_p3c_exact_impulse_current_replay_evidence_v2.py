"""Mutation tests for additive T08 recovered-ADS replay evidence."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_p3c_exact_impulse_current_replay_evidence_v2",
    ROOT / "tools" / "verify_p3c_exact_impulse_current_replay_evidence_v2.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class ExactImpulseCurrentReplayEvidenceV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(
            (ROOT / "docs/baselines/p3c-exact-impulse-current-replay-evidence.v2.yaml").read_text(
                encoding="utf-8"
            )
        )

    def test_current_record_is_valid_and_not_promoted(self) -> None:
        result = GATE.verify_document(self.document, check_archive=False)
        self.assertTrue(result["valid"])
        self.assertFalse(result["within_one_percent"])
        self.assertFalse(result["release_promoted"])

    def test_clean_archive_inventory_is_bound(self) -> None:
        baseline = self.document["baseline"]
        self.assertEqual(GATE._archive_inventory(ROOT, set(baseline["source_inventory"])), baseline["source_inventory"])
        GATE._verify_archive(ROOT, baseline["source_inventory"])

    def test_identity_and_metric_mutations_fail_closed(self) -> None:
        mutations = (
            ("manifest_audit", lambda value: value["recovered_original_ads_custody"]["netlist_actual_retained_bytes"].__setitem__("sha256", "0" * 64)),
            ("candidate_reference", lambda value: value["candidate_reference"].__setitem__("candidate_payload_sha256", "0" * 64)),
            ("candidate_reference", lambda value: value["candidate_reference"].__setitem__("waveform_nrmse_bits", "3f847ae147ae147b")),
            ("admission", lambda value: value["admission"].__setitem__("strict_index_compare_accepted", True)),
            ("external_report", lambda value: value["external_report"].__setitem__("byte_length", 0)),
            ("observer", lambda value: value["observer"].__setitem__("sha256", "0" * 64)),
        )
        for reason, mutation in mutations:
            with self.subTest(reason=reason):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaisesRegex(GATE.VerificationError, reason):
                    GATE.verify_document(value, check_archive=False)

    def test_policy_and_provenance_mutations_fail_closed(self) -> None:
        mutations = (
            ("policy", lambda value: value["policy"].__setitem__("alignment", "allowed")),
            ("predecessor", lambda value: value["predecessor"].__setitem__("blocked_v1_rewritten", True)),
            ("non_claims", lambda value: value["non_claims"].append("C:\\external\\payload.bin")),
            ("manifest_audit", lambda value: value["recovered_original_ads_custody"]["identity_checks"].__setitem__("dataset_identity", "unverified")),
        )
        for reason, mutation in mutations:
            with self.subTest(reason=reason):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaisesRegex(GATE.VerificationError, reason):
                    GATE.verify_document(value, check_archive=False)


if __name__ == "__main__":
    unittest.main()
