from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_clean_room_register import _hash_material_ids, _load_document, verify_document


def registry() -> dict:
    material = {
        "id": "public-standard",
        "kind": "public_standard",
        "content_sha256": "a" * 64,
        "provenance": {"source_ref": "https://example.invalid/standard-v1", "license_evidence": "public-standard"},
        "allowed_roles": ["observer", "spec_author", "implementer", "comparator", "auditor"],
        "derived_from": [],
    }
    principals = [
        {"id": role, "roles": [role], "identity_ref": f"identity/{role}", "status": "active"}
        for role in ("observer", "spec_author", "implementer", "comparator", "auditor")
    ]
    scope = {
        "id": "scope",
        "paths": ["crates/example/**"],
        "state": "planned",
        "role_material_allowlists": {
            "observer": ["public-standard"],
            "spec_author": ["public-standard"],
            "implementer": ["public-standard"],
            "comparator": ["public-standard"],
            "auditor": ["public-standard"],
        },
    }
    return {
        "schema": "sipi.clean-room-register.v1",
        "status": "provisional",
        "policy": {
            "implementation_allowed": ["public_standard", "mit_source", "independent_spec"],
            "implementation_forbidden": ["non_mit_source", "pybert_source", "oracle_fixture", "prohibited_implementation_input"],
        },
        "principals": principals,
        "materials": [material],
        "scopes": [scope],
        "attestations": [],
    }


def strict_registry() -> dict:
    document = registry()
    document["status"] = "strict"
    document["scopes"][0]["state"] = "audit_accepted"
    material_hash = _hash_material_ids({"public-standard"})
    phases = [
        ("observation_sealed", "observer", "observation_materials_sealed"),
        ("spec_sealed", "spec_author", "independent_spec_sealed"),
        ("implementation_attested", "implementer", "implementation_allowlist_attested"),
        ("comparison_attested", "comparator", "comparison_boundary_attested"),
        ("audit_accepted", "auditor", "clean_room_audit_accepted"),
    ]
    document["attestations"] = [
        {
            "id": f"attestation-{phase}",
            "scope": "scope",
            "phase": phase,
            "principal": principal,
            "role": principal,
            "subject_sha256": hashlib.sha256(phase.encode()).hexdigest(),
            "material_set_sha256": material_hash,
            "statement": statement,
            "evidence_refs": [f"evidence/{phase}.json"],
            "created_at": "2026-08-09T00:00:00Z",
            "signature_ref": f"signatures/{phase}.sig",
        }
        for phase, principal, statement in phases
    ]
    return document


class CleanRoomRegisterTests(unittest.TestCase):
    def test_current_register_is_valid_and_provisional(self) -> None:
        report = verify_document(_load_document(ROOT / "clean-room-register.v1.yaml"))
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["status"], "provisional")
        self.assertEqual(report["attestation_count"], 0)

    def test_valid_planned_and_strict_attested_documents(self) -> None:
        report = verify_document(registry())
        self.assertTrue(report["valid"], report["blockers"])
        report = verify_document(strict_registry())
        self.assertTrue(report["valid"], report["blockers"])

    def test_unknown_fields_and_unsafe_references_fail_closed(self) -> None:
        invalid = registry()
        invalid["unexpected"] = True
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("top-level" in item for item in report["blockers"]))

        invalid = registry()
        invalid["principals"][0]["identity_ref"] = "C:/Users/private/identity"
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("unsafe identity_ref" in item for item in report["blockers"]))

    def test_prohibited_transitive_ancestor_and_role_misuse_fail_closed(self) -> None:
        invalid = registry()
        invalid["materials"].append(
            {
                "id": "pybert-source",
                "kind": "pybert_source",
                "content_sha256": "b" * 64,
                "provenance": {"source_ref": "external/pybert", "license_evidence": "external/license"},
                "allowed_roles": ["observer"],
                "derived_from": [],
            }
        )
        invalid["materials"][0]["derived_from"] = ["pybert-source"]
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("forbidden ancestor" in item for item in report["blockers"]))

        invalid = registry()
        invalid["scopes"][0]["role_material_allowlists"]["observer"] = ["missing"]
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("invalid observer allowlist" in item for item in report["blockers"]))

    def test_attestation_hash_signature_and_role_separation_fail_closed(self) -> None:
        invalid = strict_registry()
        invalid["attestations"][0]["material_set_sha256"] = "0" * 64
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("material_set_sha256 mismatch" in item for item in report["blockers"]))

        invalid = strict_registry()
        invalid["attestations"][0]["signature_ref"] = None
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("requires signature_ref" in item for item in report["blockers"]))

        invalid = strict_registry()
        invalid["principals"][0]["roles"].append("implementer")
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("principal separation" in item for item in report["blockers"]))

    def test_missing_phase_and_release_mode_fail_closed(self) -> None:
        invalid = strict_registry()
        invalid["attestations"].pop()
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("missing required attestations" in item for item in report["blockers"]))

        report = verify_document(registry(), release=True)
        self.assertFalse(report["valid"])
        self.assertTrue(any("cannot authorize a release" in item for item in report["blockers"]))

    def test_independent_spec_hash_is_checked_when_local(self) -> None:
        invalid = copy.deepcopy(_load_document(ROOT / "clean-room-register.v1.yaml"))
        invalid["materials"][0]["content_sha256"] = "0" * 64
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("content hash mismatch" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
