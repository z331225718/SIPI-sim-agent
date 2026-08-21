"""Mutation tests for the P5 T13 R4.80 custody gate."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_r480_reference_custody_preflight as GATE


class ReferenceCustodyPreflightTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(yaml.safe_load(GATE.BASELINE.read_text(encoding="utf-8")))

    def assert_invalid(self, document: dict, reason: str) -> None:
        result = GATE.verify_document(document, ROOT)
        self.assertFalse(result["valid"], result)
        self.assertIn(reason, result["blockers"], result)
        self.assertFalse(result["t14_full_compare_matrix_admitted"])

    def test_current_record_is_valid_but_t14_remains_blocked(self) -> None:
        result = GATE.verify_document(self.document(), ROOT)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["t14_full_compare_matrix_admitted"])
        self.assertEqual(result["blockers"], [])

    def test_external_object_and_registry_mutations_fail_closed(self) -> None:
        document = self.document()
        document["external_source"]["capability_object"]["git_blob"] = "0" * 40
        self.assert_invalid(document, "external_source_object_identity_invalid")

        document = self.document()
        document["external_source"]["capability_registry_copy"]["content_sha256"] = "0" * 64
        self.assert_invalid(document, "capability_registry_conflict_record_invalid")

        document = self.document()
        document["external_materials"]["selected"][1]["sha256"] = "0" * 64
        self.assert_invalid(document, "external_material_identity_mismatch")

        document = self.document()
        document["hash_bindings"]["material_registry"]["path"] = "C:/external/registry.yaml"
        self.assert_invalid(document, "hash_binding_record_invalid:material_registry")

    def test_runner_identity_and_authorization_mutations_fail_closed(self) -> None:
        document = self.document()
        document["runner"]["capability_preflight"]["isolation"]["startup_isolation"] = "proved"
        self.assert_invalid(document, "runner_capability_record_invalid")

        document = self.document()
        document["runner"]["invocation_surface"]["execution"]["authorized"] = True
        self.assert_invalid(document, "runner_invocation_record_invalid")

        document = self.document()
        document["runner"]["historical_first_run"]["replay_manifest"] = "available"
        self.assert_invalid(document, "historical_first_run_record_invalid")

    def test_input_default_warning_and_checkpoint_mutations_fail_closed(self) -> None:
        document = self.document()
        document["canonical_inputs"]["normalized_input_digest"]["value"] = "0" * 64
        self.assert_invalid(document, "canonical_input_record_invalid")

        document = self.document()
        document["defaults"]["caller_dependent_defaults"] = 0
        self.assert_invalid(document, "default_custody_record_invalid")

        document = self.document()
        document["warnings"]["static_observation"]["warning_call_count"] = 24
        self.assert_invalid(document, "warning_custody_record_invalid")

        document = self.document()
        document["checkpoints"]["case_checkpoint_digests"]["case_1"] = "0" * 64
        self.assert_invalid(document, "checkpoint_custody_record_invalid")

    def test_metrics_tolerance_artifact_and_admission_mutations_fail_closed(self) -> None:
        document = self.document()
        document["metrics"]["surface"]["output_metric_keys"].append("TDILN_dB")
        self.assert_invalid(document, "metric_custody_record_invalid")

        document = self.document()
        document["tolerance"]["observed_c4_policy"]["relative_tolerance"] = 0.1
        self.assert_invalid(document, "tolerance_record_invalid")

        document = self.document()
        document["artifacts"]["first_run"]["summary_json_sha256"] = "0" * 64
        self.assert_invalid(document, "artifact_custody_record_invalid")

        document = self.document()
        document["admission"]["t14_full_compare_matrix_admitted"] = True
        self.assert_invalid(document, "admission_record_not_fail_closed")

    def test_product_self_comparison_cannot_become_oracle(self) -> None:
        document = self.document()
        document["scope"]["product_self_comparison_as_oracle"] = "allowed"
        self.assert_invalid(document, "scope_boundary_invalid")

        document = self.document()
        document["non_claims"] = []
        self.assert_invalid(document, "non_claims_invalid")

    def test_unknown_top_level_field_is_rejected(self) -> None:
        document = self.document()
        document["oracle_result"] = {"status": "accepted"}
        self.assert_invalid(document, "baseline_shape_invalid")


if __name__ == "__main__":
    unittest.main()
