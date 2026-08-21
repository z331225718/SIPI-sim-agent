"""Contract tests for the P7 currentness/NOTICE reconciliation."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p7_license_notice_currentness",
    ROOT / "tools" / "verify_p7_license_notice_currentness_reconciliation.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
DOCUMENT = ROOT / "docs" / "baselines" / "p7-license-notice-currentness-reconciliation.v1.yaml"


class LicenseNoticeCurrentnessTests(unittest.TestCase):
    def document(self) -> dict:
        value = yaml.safe_load(DOCUMENT.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        return value

    def test_document_is_valid_but_currentness_is_blocked(self) -> None:
        document = self.document()
        VERIFY.validate(document)
        self.assertEqual(document["currentness"]["state"], "historical_source_drift_and_external_bytes_missing")
        self.assertFalse(document["gates"]["current_package_set_observed"])
        self.assertFalse(document["gates"]["current_license_file_material_observed"])
        self.assertFalse(document["gates"]["release_ready"])

    def test_source_drift_cannot_be_reclassified_as_current(self) -> None:
        document = copy.deepcopy(self.document())
        document["currentness"]["candidate_cargo_lock_matches_baseline"] = True
        with self.assertRaisesRegex(VERIFY.ReconciliationError, "currentness_binding_invalid"):
            VERIFY.validate(document)

    def test_material_gap_cannot_be_rewritten_as_absence(self) -> None:
        document = copy.deepcopy(self.document())
        document["historical_build"]["material_identity"]["notice_candidates"] = "none_observed"
        with self.assertRaisesRegex(VERIFY.ReconciliationError, "historical_material_identity_invalid"):
            VERIFY.validate(document)

    def test_external_reports_are_optional_only_as_historical_inputs(self) -> None:
        document = self.document()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_bytes(b"{}")
            with self.assertRaisesRegex(VERIFY.ReconciliationError, "historical_build_report_identity_mismatch"):
                VERIFY.verify_external_pair(path, path, document)

    def test_category_counts_are_hash_bound(self) -> None:
        document = copy.deepcopy(self.document())
        document["normalization"]["category_counts"]["declared_string_unparsed"] = 74
        with self.assertRaisesRegex(VERIFY.ReconciliationError, "normalization_category_counts_invalid"):
            VERIFY.validate(document)


if __name__ == "__main__":
    unittest.main()
