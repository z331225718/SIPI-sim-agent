from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_license_manifest import verify


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def subject(**changes) -> dict:
    value = {
        "id": "test-source",
        "subject_type": "source",
        "scope": {"root_ref": "fixture", "paths": ["src"]},
        "fixture_refs": [],
        "license_declaration": "BSD-3-Clause",
        "evidence_refs": [{"type": "formal_license_text", "path": "LICENSE", "sha256": "X"}],
        "distribution_status": "authorized_public",
        "compliance": {"state": "authorized", "notice": "retain notice"},
        "owners": {"asset_owner": "fixture-maintainer", "license_decision_owner": "fixture-license-owner", "gate_owner": "gate"},
        "required_by": ["G0b"],
        "status_reason": "license-owner confirmed coverage",
    }
    value.update(changes)
    return value


def manifest(subjects: list, *, open_authorizations: list | None = None) -> str:
    import yaml

    return yaml.safe_dump(
        {
            "schema": "sipi.license-manifest.v1",
            "status": "provisional",
            "default_distribution_status": "blocked_unknown",
            "policy": {"valid_distribution_statuses": ["authorized_public", "authorized_private", "external_reference_only", "blocked_unknown"]},
            "subjects": subjects,
            "open_authorizations": open_authorizations or [],
            "open_classification": [],
            "uncovered_paths": [],
            "non_claims": [],
        }
    )


class LicenseManifestVerifierTests(unittest.TestCase):
    def test_all_blocked_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = verify(manifest([subject(distribution_status="blocked_unknown")]), root)
        self.assertTrue(report["valid"], report["blockers"])

    def test_authorized_without_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = verify(manifest([subject(evidence_refs=[])]), root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("evidence_refs" in item for item in report["blockers"]))

    def test_authorized_with_resolved_owner_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            license_path = root / "LICENSE"
            license_path.write_text("BSD-3-Clause text", encoding="utf-8")
            report = verify(manifest([subject(evidence_refs=[{"type": "formal_license_text", "path": "LICENSE", "sha256": sha256(license_path)}])]), root)
        self.assertTrue(report["valid"], report["blockers"])

    def test_evidence_hash_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "LICENSE").write_text("other text", encoding="utf-8")
            report = verify(manifest([subject(evidence_refs=[{"type": "formal_license_text", "path": "LICENSE", "sha256": "F" * 64}])]), root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("hash mismatch" in item for item in report["blockers"]))

    def test_pending_decision_owner_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = verify(manifest([subject(owners={"asset_owner": "x", "license_decision_owner": "pending_external_authorization", "gate_owner": "g"})]), root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("unresolved" in item for item in report["blockers"]))

    def test_authorized_public_requires_declaration_and_compliance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = verify(manifest([subject(license_declaration="NOASSERTION", compliance={"state": "blocked", "notice": "x"})]), root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("license declaration" in item for item in report["blockers"]))
        self.assertTrue(any("authorized/complete compliance" in item for item in report["blockers"]))

    def test_open_authorization_conflict_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = verify(manifest([subject()], open_authorizations=[{"subject_id": "test-source", "owner": "x", "required_evidence": "y"}]), root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("open_authorizations" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
