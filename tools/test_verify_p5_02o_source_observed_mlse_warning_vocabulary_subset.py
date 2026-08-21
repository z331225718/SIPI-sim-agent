"""Mutation tests for the evidence-only P5-02o vocabulary subset."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import verify_p5_02o_source_observed_mlse_warning_vocabulary_subset as GATE


class MlseWarningVocabularySubsetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.EVIDENCE)

    def test_current_document_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["entry_count"], 3)
        self.assertEqual(result["inherited_warning_count"], 25)

    def test_rejects_entry_mutations(self) -> None:
        mutations = (
            lambda document: document["entries"].pop(),
            lambda document: document["entries"].append(copy.deepcopy(document["entries"][0])),
            lambda document: document["entries"][0].__setitem__("message", "changed"),
            lambda document: document["entries"].reverse(),
        )
        for mutate in mutations:
            document = copy.deepcopy(self.document)
            mutate(document)
            with self.subTest(mutate=mutate):
                with self.assertRaises(GATE.VocabularyError):
                    GATE.validate(document)

    def test_rejects_msgbox_promoted_to_warning(self) -> None:
        document = copy.deepcopy(self.document)
        document["excluded_callsite"]["callable"] = "warning"
        with self.assertRaisesRegex(GATE.VocabularyError, "excluded_callsite_invalid"):
            GATE.validate(document)

    def test_rejects_source_or_inherited_record_drift(self) -> None:
        for key in ("commit", "git_blob_oid_sha1", "normalized_content_sha256"):
            document = copy.deepcopy(self.document)
            document["source"][key] = "0" * len(document["source"][key])
            with self.subTest(key=key):
                with self.assertRaisesRegex(GATE.VocabularyError, "source_identity_invalid"):
                    GATE.validate(document)
        document = copy.deepcopy(self.document)
        document["inherited_records"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.VocabularyError, "inherited_records_invalid"):
            GATE.validate(document)

    def test_rejects_scope_or_nonclaim_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["scope"]["runtime_detector"] = "implemented"
        with self.assertRaisesRegex(GATE.VocabularyError, "scope_invalid"):
            GATE.validate(document)
        document = copy.deepcopy(self.document)
        document["non_claims"].remove("not_acceptance")
        with self.assertRaisesRegex(GATE.VocabularyError, "non_claims_invalid"):
            GATE.validate(document)

    def test_rejects_product_rust_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            module = Path(temporary) / "source_warning_catalog_v1.rs"
            module.write_text("unexpected", encoding="utf-8")
            with mock.patch.object(GATE, "REMOVED_RUST_MODULE", module):
                with self.assertRaisesRegex(GATE.VocabularyError, "product_rust_module_present"):
                    GATE.validate(self.document)


if __name__ == "__main__":
    unittest.main()
