"""Focused mutation tests for the root COM direct-port link record."""

from __future__ import annotations

import unittest

from tools.verify_com_r480_root_integration import reachable_packages, validate_document


def document() -> dict:
    return {
        "schema": "sipi.com.r480-root-integration.v1",
        "status": "internal_feature_linked_non_distributed",
        "candidate": {"commit": "a" * 40, "tree": "b" * 40},
        "feature": "com-direct-integration",
        "default_cli_excludes_direct": True,
        "root_feature_closure": {"package_count": 1, "sha256": "c" * 64},
        "candidate_evidence": [{"path": "Cargo.lock", "sha256": "d" * 64}],
        "non_claims": ["no_public_com_run_route", "no_public_request_or_result_wire", "no_distribution_admission", "no_release_admission"],
    }


class RootIntegrationTests(unittest.TestCase):
    def test_valid_document(self) -> None:
        validate_document(document())

    def test_release_claim_is_rejected(self) -> None:
        value = document()
        value["non_claims"] = value["non_claims"][:-1]
        with self.assertRaisesRegex(ValueError, "non-claims"):
            validate_document(value)

    def test_default_feature_must_exclude_direct(self) -> None:
        value = document()
        value["default_cli_excludes_direct"] = False
        with self.assertRaisesRegex(ValueError, "default route"):
            validate_document(value)

    def test_unknown_key_is_rejected(self) -> None:
        value = document()
        value["distribution_admitted"] = True
        with self.assertRaisesRegex(ValueError, "keys"):
            validate_document(value)

    def test_metadata_requires_license_receipts(self) -> None:
        metadata = {
            "resolve": {"root": "root", "nodes": [{"id": "root", "dependencies": []}]},
            "packages": [{"id": "root", "name": "sipi-cli", "version": "0.1.0", "license": None, "source": None}],
        }
        with self.assertRaisesRegex(ValueError, "license receipt"):
            reachable_packages(metadata)


if __name__ == "__main__":
    unittest.main()
