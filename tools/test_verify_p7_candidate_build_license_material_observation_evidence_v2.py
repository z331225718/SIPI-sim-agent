"""Contract tests for the P7 actual-build Cargo license-material observation."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_license_evidence_v2", ROOT / "tools" / "verify_p7_candidate_build_license_material_observation_evidence_v2.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(VERIFY)
DOCUMENT_PATH = ROOT / "docs" / "baselines" / "p7-candidate-build-license-material-observation-evidence.v2.yaml"


class CandidateBuildLicenseMaterialEvidenceV2Tests(unittest.TestCase):
    def document(self) -> dict:
        value = yaml.safe_load(DOCUMENT_PATH.read_text(encoding="utf-8")); assert isinstance(value, dict); return value

    def test_document_is_valid_and_stays_non_conclusive(self) -> None:
        document = self.document(); VERIFY.validate(document)
        self.assertTrue(document["gates"]["selected_windows_build_package_set_observed"])
        self.assertFalse(document["gates"]["dependency_snapshot_ready"])
        self.assertFalse(document["gates"]["release_ready"])

    def test_external_report_is_exactly_bound(self) -> None:
        document = self.document()
        report = {
            "schema": VERIFY.REPORT_SCHEMA,
            "status": document["result"]["status"],
            "candidate": document["candidate"],
            "build": {
                "cargo_version_sha256": "a" * 64,
                "target": "x86_64-pc-windows-msvc",
                "release": True,
                "locked": True,
                "offline": True,
                "fresh_builds": 2,
            },
            "package_set": {
                "sha256": document["result"]["package_set_sha256"],
                "counts": document["result"]["package_counts"],
                "build_a_stderr_sha256": "b" * 64,
                "build_b_stderr_sha256": "c" * 64,
                "packages": [{"identity": f"synthetic:{index}"} for index in range(86)],
            },
            "gates": VERIFY.EXPECTED_GATES,
            "non_claims": VERIFY.EXPECTED_NON_CLAIMS,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"; path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            document["external_report"] = {"sha256": VERIFY.sha256(path.read_bytes()), "bytes": path.stat().st_size}
            VERIFY.verify_external_report(document, path)
            report["package_set"]["counts"]["registry"] = 72; path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.EvidenceError, "external_report_identity_mismatch"):
                VERIFY.verify_external_report(document, path)

    def test_promotion_or_historical_rewrite_fails_closed(self) -> None:
        document = self.document(); document["gates"]["release_ready"] = True
        with self.assertRaisesRegex(VERIFY.EvidenceError, "blocked_gates_invalid"): VERIFY.validate(document)
        document = self.document(); document["historical_predecessor"]["status"] = "current"
        with self.assertRaisesRegex(VERIFY.EvidenceError, "historical_predecessor_invalid"): VERIFY.validate(document)
        document = copy.deepcopy(self.document()); document["result"]["package_counts"]["total"] = 87
        with self.assertRaisesRegex(VERIFY.EvidenceError, "result_invalid"): VERIFY.validate(document)


if __name__ == "__main__":
    unittest.main()
