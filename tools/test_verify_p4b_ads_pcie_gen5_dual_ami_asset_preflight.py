"""Negative tests for the dual-AMI external-only preflight gate."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dual_ami_gate", ROOT / "tools/verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class DualAmiAssetPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml").read_text(encoding="utf-8"))

    def verify(self, document: dict) -> dict:
        return GATE.verify_manifest(ROOT, document, hashes=set())

    def test_current_record_stays_external_only_and_worker_blocked(self) -> None:
        report = self.verify(self.document)
        self.assertEqual(report["status"], "external_only_identity_observed_worker_blocked")
        self.assertFalse(report["worker_admitted"])
        self.assertFalse(report["runtime_evidence"])

    def test_promotion_and_asset_identity_drift_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["asset_set"]["worker_admission"] = "admitted"
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["asset_set"]["assets"][0]["sha256"] = "0" * 64
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)

    def test_swapped_binding_path_leak_and_closure_promotion_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["asset_set"]["bindings"][0]["dll_asset"] = "pcie-rx-dll"
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["asset_set"]["assets"][0]["logical_name"] = r"C:\\vendor\\pcie_gen5.ibs"
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["asset_set"]["static_abi_surface"]["dynamic_dependency_closure"] = "complete"
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)

    def test_tracked_vendor_bytes_and_owner_scope_expansion_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        vendor_hash = document["asset_set"]["assets"][0]["sha256"]
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_manifest(ROOT, document, hashes={vendor_hash})
        report_hash = document["external_observation"]["report_content_sha256"]
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_manifest(ROOT, document, hashes={report_hash})
        document = copy.deepcopy(self.document)
        document["owner_authorization"]["scope"] = "external_worker_candidate"
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)

    def test_non_claims_are_exact_and_cannot_be_weakened(self) -> None:
        document = copy.deepcopy(self.document)
        document["non_claims"][4] = "Not ADS acceptance."
        with self.assertRaises(GATE.PreflightError):
            self.verify(document)


if __name__ == "__main__":
    unittest.main()
