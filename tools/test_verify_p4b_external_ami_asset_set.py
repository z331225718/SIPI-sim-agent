"""Contract tests for the external AMI asset-set admission gate."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4b_assets", ROOT / "tools" / "verify_p4b_external_ami_asset_set.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class ExternalAmiAssetSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = yaml.safe_load((ROOT / "docs/baselines/p4b-external-ami-asset-set.v1.yaml").read_text(encoding="utf-8"))

    def test_current_asset_set_is_external_and_not_worker_admitted(self) -> None:
        report = GATE.verify_manifest(ROOT, self.manifest, tracked_hashes=set())
        self.assertEqual(report["status"], "external_only_admission_blocked")
        self.assertFalse(report["worker_admitted"])
        self.assertEqual(report["packaging"], "prohibited")

    def test_missing_closure_and_identity_role_mismatch_are_not_promotable(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["asset_set"]["worker_admission"] = "admitted"
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())
        manifest = copy.deepcopy(self.manifest)
        manifest["asset_set"]["bindings"][0]["status"] = "admitted"
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())

    def test_identity_authorization_and_prior_evidence_drift_are_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["asset_set"]["assets"][0]["sha256"] = "0" * 64
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())
        manifest = copy.deepcopy(self.manifest)
        manifest["owner_authorization"]["scope"] = "external_worker_candidate"
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())
        manifest = copy.deepcopy(self.manifest)
        manifest["prior_observation_evidence"][0]["sha256"] = "0" * 64
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())

    def test_vendor_asset_leak_and_external_path_are_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        hashes = {manifest["asset_set"]["assets"][2]["sha256"]}
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=hashes)
        manifest = copy.deepcopy(self.manifest)
        manifest["asset_set"]["assets"][0]["source"]["path"] = "C:/external/example_rx.ibs"
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())
        self.assertFalse(GATE.relative_source_path("C:/external/example_rx.ibs"))
        manifest = copy.deepcopy(self.manifest)
        manifest["asset_set"]["assets"][2]["logical_name"] = r"C:\\external\\example_rx.dll"
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())

    def test_unknown_fields_duplicate_hash_and_fake_rights_clear_are_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["unexpected"] = True
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())
        manifest = copy.deepcopy(self.manifest)
        manifest["asset_set"]["assets"][1]["sha256"] = manifest["asset_set"]["assets"][0]["sha256"]
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())
        manifest = copy.deepcopy(self.manifest)
        manifest["asset_set"]["assets"][0]["third_party_rights_status"] = "license_cleared"
        with self.assertRaises(GATE.AssetSetError):
            GATE.verify_manifest(ROOT, manifest, tracked_hashes=set())


if __name__ == "__main__":
    unittest.main()
