"""Contract tests for the rejected P7 Cargo license-material observation."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p7_license_evidence", ROOT / "tools" / "verify_p7_candidate_build_license_material_observation_evidence.py"
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
DOCUMENT_PATH = ROOT / "docs" / "baselines" / "p7-candidate-build-license-material-observation-evidence.v1.yaml"


class CandidateBuildLicenseMaterialEvidenceTests(unittest.TestCase):
    def document(self) -> dict:
        value = yaml.safe_load(DOCUMENT_PATH.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        return value

    def report_for(self, document: dict) -> bytes:
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
                "rejection_stage": "build_closure",
                "rejection_reason": "cargo_metadata_failed",
            },
            "gates": VERIFY.EXPECTED_GATES,
            "non_claims": VERIFY.EXPECTED_NON_CLAIMS,
        }
        return json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"

    def test_document_is_valid_and_keeps_release_blocked(self) -> None:
        document = self.document()
        VERIFY.validate(document)
        self.assertFalse(document["gates"]["release_ready"])
        self.assertEqual(document["gates"]["promotion_status"], "blocked")

    def test_external_rejected_report_is_exactly_bound(self) -> None:
        document = self.document()
        raw = self.report_for(document)
        document["external_report"] = {"sha256": VERIFY.sha256(raw), "bytes": len(raw)}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_bytes(raw)
            VERIFY.verify_external_report(document, path)
            tampered = json.loads(raw)
            tampered["build"]["rejection_reason"] = "network_retry"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.EvidenceError, "external_report_identity_mismatch"):
                VERIFY.verify_external_report(document, path)

    def test_gate_and_observer_identity_promotions_fail_closed(self) -> None:
        document = self.document()
        document["gates"]["release_ready"] = True
        with self.assertRaisesRegex(VERIFY.EvidenceError, "blocked_gates_invalid"):
            VERIFY.validate(document)
        document = self.document()
        document["observer"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(VERIFY.EvidenceError, "observer_source_mismatch"):
            VERIFY.validate(document)
        document = self.document()
        document["result"]["package_set_observed"] = True
        with self.assertRaisesRegex(VERIFY.EvidenceError, "result_invalid"):
            VERIFY.validate(document)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
