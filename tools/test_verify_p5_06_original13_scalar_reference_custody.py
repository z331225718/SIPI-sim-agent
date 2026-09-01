"""Mutation coverage for original-13 scalar-reference custody."""
from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

try:
    from . import verify_p5_06_original13_scalar_reference_custody as subject
except ImportError:
    import verify_p5_06_original13_scalar_reference_custody as subject


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / subject.MANIFEST
MATLAB_REPORT = ROOT / "docs/baselines/p5-06-original13-root-matrix-v6-matlab-01.json"


class ScalarReferenceCustodyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.report = json.loads(MATLAB_REPORT.read_text(encoding="utf-8"))

    def assert_rejected(self, document: dict[str, object]) -> None:
        with self.assertRaises(subject.VerificationError):
            subject.validate(document, ROOT)

    def test_live_record_is_valid(self) -> None:
        self.assertTrue(subject.validate(self.document, ROOT)["valid"])

    def test_workbook_or_parameter_digest_drift_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["normalized_inputs"]["sha256"] = "0" * 64
        self.assert_rejected(changed)

    def test_channel_role_manifest_drift_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["scope"]["channels"] = ["FEXT", "THRU", "NEXT"]
        self.assert_rejected(changed)

    def test_reference_bundle_replacement_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["reference_bundle"]["matlab_sha256"] = "0" * 64
        self.assert_rejected(changed)

    def test_tolerance_relaxation_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["comparison_policy"]["cross_tolerance"] = 1.0e-6
        self.assert_rejected(changed)

    def test_oracle_identity_replacement_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["oracle_runtime"]["matlab"]["release"] = "R2026a"
        self.assert_rejected(changed)

    def test_candidate_report_replacement_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["reports"][2]["sha256"] = "0" * 64
        self.assert_rejected(changed)

    def test_nonce_reuse_policy_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["custody"]["nonce_distinct"] = False
        self.assert_rejected(changed)

    def test_slot_reordering_changes_bundle(self) -> None:
        changed = copy.deepcopy(self.report)
        changed["records"][0]["metrics"].reverse()
        self.assertNotEqual(subject.scalar_bundle(self.report), subject.scalar_bundle(changed))

    def test_added_or_deleted_slot_changes_bundle(self) -> None:
        changed = copy.deepcopy(self.report)
        del changed["records"][0]["metrics"][0]["COM_dB"]
        self.assertNotEqual(subject.scalar_bundle(self.report), subject.scalar_bundle(changed))

    def test_infinity_sign_changes_bundle(self) -> None:
        changed = copy.deepcopy(self.report)
        for record in changed["records"]:
            for case in record["metrics"]:
                if case.get("ERL") == "+Inf":
                    case["ERL"] = "-Inf"
                    self.assertNotEqual(subject.scalar_bundle(self.report), subject.scalar_bundle(changed))
                    return
        self.fail("fixture has no infinity")

    def test_nan_is_rejected(self) -> None:
        changed = copy.deepcopy(self.report)
        changed["records"][0]["metrics"][0]["COM_dB"] = math.nan
        with self.assertRaises(subject.VerificationError):
            subject.scalar_bundle(changed)


if __name__ == "__main__":
    unittest.main()
