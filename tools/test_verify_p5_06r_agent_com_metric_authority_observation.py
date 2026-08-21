"""Mutation tests for the additive P5-06r authority observation."""

from __future__ import annotations

import copy
import os
import unittest
from pathlib import Path

import yaml

from tools import verify_p5_06r_agent_com_metric_authority_observation as verifier


EXTERNAL_ROOT = Path(os.environ.get("SIPI_COM_ROOT", str(verifier.ROOT.parent / "COM")))
EXTERNAL_AVAILABLE = (EXTERNAL_ROOT / ".git").exists()


class P506RAuthorityObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(verifier.EVIDENCE.read_text(encoding="utf-8"))

    def assert_invalid(self, mutate) -> None:
        candidate = copy.deepcopy(self.document)
        mutate(candidate)
        with self.assertRaises(verifier.ObservationError):
            verifier.validate_document(candidate)

    def test_baseline(self) -> None:
        result = verifier.validate_document(self.document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["missing_required_metrics"], ["TD_ILN_dB"])

    @unittest.skipUnless(EXTERNAL_AVAILABLE, "canonical external COM Git checkout is unavailable")
    def test_pinned_source_objects(self) -> None:
        result = verifier.validate_document(self.document, source_root=EXTERNAL_ROOT)
        self.assertTrue(result["source_object_checked"])

    def test_schema_mutation(self) -> None:
        self.assert_invalid(lambda doc: doc.__setitem__("schema", "wrong"))

    def test_reflective_input_mutation(self) -> None:
        self.assert_invalid(lambda doc: doc["canonical_selection"]["channel"].__setitem__("sha256", "0" * 64))

    def test_payload_hash_mutation(self) -> None:
        self.assert_invalid(lambda doc: doc["runs"]["payloads"][0].__setitem__("sha256", "0" * 64))

    def test_td_iln_scalar_fabrication_rejected(self) -> None:
        self.assert_invalid(lambda doc: doc["runs"]["cases"][0].__setitem__("TD_ILN_dB", 22.366448964047528))

    def test_fom_alias_mutation_rejected(self) -> None:
        self.assert_invalid(lambda doc: doc["required_metric_surface"]["auxiliary_non_substitutes"][0].__setitem__("allowed", True))

    def test_icn_alias_mutation_rejected(self) -> None:
        self.assert_invalid(lambda doc: doc["required_metric_surface"]["auxiliary_non_substitutes"][1].__setitem__("allowed_as", "COM_dB"))

    def test_transition_promotion_rejected(self) -> None:
        self.assert_invalid(lambda doc: doc["p3c_03_transition"]["semantics_to_external_compare"].__setitem__("decision", "admitted"))

    def test_crate_scope_mutation_rejected(self) -> None:
        self.assert_invalid(lambda doc: doc["p3c_03_transition"]["typed_compare_existing"].__setitem__("product_crate_changed_in_this_slice", True))

    def test_source_object_mutation_rejected(self) -> None:
        self.assert_invalid(lambda doc: doc["source_objects"][0].__setitem__("git_blob", "0" * 40))

    def test_audit_binding_mutation(self) -> None:
        self.assert_invalid(lambda doc: doc["audit"].__setitem__("sha256", "0" * 64))

    def test_absolute_path_mutation(self) -> None:
        self.assert_invalid(lambda doc: doc["canonical_selection"]["config"].__setitem__("path", "C:/secret/config.xlsx"))


if __name__ == "__main__":
    unittest.main()
