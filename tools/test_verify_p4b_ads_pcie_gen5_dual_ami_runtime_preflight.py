"""Mutation tests for the fail-closed P4B vendor AMI runtime preflight."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4b_runtime_preflight", ROOT / "tools/verify_p4b_ads_pcie_gen5_dual_ami_runtime_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class RuntimePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-runtime-preflight.v1.yaml").read_text(encoding="utf-8"))

    def verify(self, document: dict) -> dict:
        return GATE.verify_manifest(ROOT, document, hashes=set())

    def test_current_baseline_is_structured_and_blocked(self) -> None:
        result = self.verify(self.document)
        self.assertEqual(result["status"], "blocked_external_rights_or_runtime_evidence_missing")
        self.assertEqual(result["component_status"]["asset_identity"], "ready")
        self.assertEqual(result["component_status"]["static_pe_imports"], "ready")
        for name in ("rights", "parameter_compatibility", "dynamic_dependency_closure", "isolated_worker", "fresh_runtime_observation"):
            self.assertEqual(result["component_status"][name], "blocked")
        self.assertFalse(result["worker_admitted"])
        self.assertFalse(result["runtime_ready"])
        self.assertFalse(result["static_imports_substitute_runtime"])

    def test_exact_asset_identity_rights_and_parameter_mutations_reject(self) -> None:
        document = copy.deepcopy(self.document)
        document["asset_identity"]["assets"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.PreflightError, "asset_identity_exact_mismatch"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["rights"]["status"] = "ready"
        with self.assertRaisesRegex(GATE.PreflightError, "rights_gate_promotion"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["parameter_compatibility"]["observed_bindings"][0]["ami_root"] = "wrong"
        with self.assertRaisesRegex(GATE.PreflightError, "parameter_compatibility_binding_invalid"):
            self.verify(document)

    def test_static_imports_cannot_be_promoted_to_runtime_or_closure(self) -> None:
        document = copy.deepcopy(self.document)
        document["static_pe_imports"]["runtime_evidence_substitute"] = True
        with self.assertRaisesRegex(GATE.PreflightError, "static_pe_gate_promotion"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["dynamic_dependency_closure"]["static_imports_are_not_closure"] = False
        with self.assertRaisesRegex(GATE.PreflightError, "closure_gate_promotion"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["dynamic_dependency_closure"]["status"] = "ready"
        with self.assertRaisesRegex(GATE.PreflightError, "closure_gate_promotion"):
            self.verify(document)

    def test_worker_and_fresh_runtime_promotion_reject(self) -> None:
        document = copy.deepcopy(self.document)
        document["isolated_worker"]["worker_admission"] = "ready"
        with self.assertRaisesRegex(GATE.PreflightError, "worker_gate_promotion"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["fresh_runtime_observation"]["product_runtime_invoked"] = True
        with self.assertRaisesRegex(GATE.PreflightError, "runtime_gate_promotion"):
            self.verify(document)

    def test_evidence_hash_and_non_claim_mutations_reject(self) -> None:
        document = copy.deepcopy(self.document)
        document["evidence_bindings"][1]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.PreflightError, "evidence_binding_hash_mismatch"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["non_claims"][2] = "static imports prove runtime"
        with self.assertRaisesRegex(GATE.PreflightError, "non_claims_or_next_inputs_invalid"):
            self.verify(document)

    def test_tracked_vendor_hash_and_unknown_field_reject(self) -> None:
        vendor_hash = self.document["asset_identity"]["assets"][0]["sha256"]
        with self.assertRaisesRegex(GATE.PreflightError, "tracked_vendor_asset_leak"):
            GATE.verify_manifest(ROOT, self.document, hashes={vendor_hash})
        document = copy.deepcopy(self.document)
        document["profile"]["unexpected"] = True
        with self.assertRaisesRegex(GATE.PreflightError, "profile_fields_invalid"):
            self.verify(document)


if __name__ == "__main__":
    unittest.main()
