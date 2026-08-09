from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_release_license_preflight import _load, verify_document


class ReleaseLicensePreflightTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(_load(ROOT / "license-manifest.v2.yaml"))

    def test_current_preflight_is_valid_but_not_release_ready(self) -> None:
        report = verify_document(self.document())
        self.assertTrue(report["valid"], report["blockers"])
        self.assertFalse(report["release_ready"])

    def test_unknown_boundary_and_legacy_mutation_fail_closed(self) -> None:
        invalid = self.document()
        invalid["unknown"] = True
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("top-level" in item for item in report["blockers"]))

        invalid = self.document()
        invalid["release_boundary"]["sha256"] = "0" * 64
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("boundary hash mismatch" in item for item in report["blockers"]))

        invalid = self.document()
        invalid["legacy_evidence"][0]["use"] = "release_runtime"
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("cannot be a release input" in item for item in report["blockers"]))

    def test_pending_dependency_requires_no_artifact_and_exact_notice(self) -> None:
        invalid = self.document()
        invalid["release_inputs"]["dependencies"] = [
            {
                "id": "dependency-a",
                "component": "a",
                "role": "runtime",
                "source": "https://example.invalid/a",
                "requested_version": "1.0.0",
                "resolved_artifact": {"version": "1.0.0", "sha256": "a" * 64},
                "declared_spdx": "MIT",
                "license_evidence_ref": "evidence/a",
                "notice_requirement": "required",
                "sbom_component_id": "pkg:cargo/a@1.0.0",
                "status": "pending",
                "owner_action": {"owner": "owner", "action": "review", "approval_ref": None},
            }
        ]
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("pending dependency cannot claim" in item for item in report["blockers"]))
        self.assertTrue(any("NOTICE decision" in item for item in report["blockers"]))

    def test_dependency_cannot_reuse_legacy_id_or_unsafe_reference(self) -> None:
        invalid = self.document()
        invalid["release_inputs"]["dependencies"] = [
            {
                "id": "legacy-license-manifest-v1",
                "component": "legacy",
                "role": "runtime",
                "source": "file:///secret",
                "requested_version": "1",
                "resolved_artifact": {"version": None, "sha256": None},
                "declared_spdx": "MIT",
                "license_evidence_ref": "evidence/license",
                "notice_requirement": "pending",
                "sbom_component_id": "pkg:cargo/legacy@1",
                "status": "pending",
                "owner_action": {"owner": "owner", "action": "review", "approval_ref": None},
            }
        ]
        invalid["release_inputs"]["notices"] = [
            {"dependency": "legacy-license-manifest-v1", "status": "pending", "source_evidence_ref": "evidence/license", "output_notice_id": "NOTICE/legacy"}
        ]
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("legacy dependency id" in item for item in report["blockers"]))

    def test_release_always_fails_for_provisional_preflight(self) -> None:
        report = verify_document(self.document(), release=True)
        self.assertFalse(report["valid"])
        self.assertTrue(any("cannot authorize a release" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
