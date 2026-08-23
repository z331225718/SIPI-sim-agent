from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_as_01_fit_sparam_clean_archive_v3 as verifier


class CleanArchiveV3Tests(unittest.TestCase):
    def document(self):
        return yaml.safe_load(verifier.MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_is_valid(self):
        result = verifier.verify()
        self.assertTrue(result["valid"], result)

    def test_source_mutation_is_rejected(self):
        document = self.document()
        document["source"]["candidate"]["tree"] = "0" * 40
        result = verifier.verify(document=document)
        self.assertFalse(result["valid"], result)

    def test_report_hash_mutation_is_rejected(self):
        document = self.document()
        document["reports"][0]["sha256"] = "0" * 64
        result = verifier.verify(document=document)
        self.assertFalse(result["valid"], result)

    def test_parity_overclaim_is_rejected(self):
        document = self.document()
        document["scope"]["parity_claim"] = True
        result = verifier.verify(document=document)
        self.assertFalse(result["valid"], result)

    def test_audit_hash_mutation_is_rejected(self):
        document = self.document()
        document["audit"]["sha256"] = "0" * 64
        result = verifier.verify(document=document)
        self.assertFalse(result["valid"], result)

    def test_absolute_path_disclosure_is_rejected(self):
        document = self.document()
        report_path = verifier.ROOT / document["reports"][0]["path"]
        report = __import__("json").loads(report_path.read_text(encoding="utf-8"))
        report["path_probe"] = r"C:\Users\leak\report.json"
        self.assertTrue(verifier._has_absolute_path(report))
        document["_path_probe"] = report
        self.assertFalse(verifier.verify(document=document)["valid"])


if __name__ == "__main__":
    unittest.main()
