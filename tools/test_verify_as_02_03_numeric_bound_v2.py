from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_as_02_03_numeric_bound_v2 as verifier
from tools import aggregate_as_02_03_numeric_bound_v2 as aggregator


class NumericBoundTests(unittest.TestCase):
    def test_manifests_are_valid(self):
        for path in verifier.MANIFESTS.values():
            result = verifier.verify(path)
            self.assertTrue(result["valid"], result)

    def test_source_mutation_is_rejected(self):
        for path in verifier.MANIFESTS.values():
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            document["source"]["candidate"]["tree"] = "0" * 40
            self.assertFalse(verifier.verify(path, document=document)["valid"])

    def test_report_hash_mutation_is_rejected(self):
        for path in verifier.MANIFESTS.values():
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            document["reports"][0]["sha256"] = "0" * 64
            self.assertFalse(verifier.verify(path, document=document)["valid"])

    def test_parity_overclaim_is_rejected(self):
        for path in verifier.MANIFESTS.values():
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            document["parity_claim"] = True
            self.assertFalse(verifier.verify(path, document=document)["valid"])

    def test_absolute_path_disclosure_is_rejected(self):
        for path in verifier.MANIFESTS.values():
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            report_path = Path(document["reports"][0]["path"])
            report = __import__("json").loads((verifier.ROOT / report_path).read_text(encoding="utf-8"))
            report["execution"]["candidate"]["stdout_tail"] = r"C:\Users\leak\out.json"
            document["reports"][0]["_probe"] = report
            self.assertTrue(verifier._has_absolute_path(report))
            self.assertFalse(verifier.verify(path, document={**document, "_probe": report})["valid"])

    def test_aggregate_rejects_absolute_path_disclosure(self):
        source = verifier.ROOT / "docs/baselines/as-02-numeric-bound-v2-run-01.json"
        report = json.loads(source.read_text(encoding="utf-8"))
        report["execution"]["candidate"]["stdout_tail"] = r"C:\Users\leak\out.json"
        with tempfile.TemporaryDirectory(dir=verifier.ROOT / "docs/baselines") as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            output = Path(directory) / "aggregate.json"
            first.write_text(json.dumps(report), encoding="utf-8")
            second.write_text(json.dumps(report), encoding="utf-8")
            result = aggregator.aggregate(first, second, output)
        self.assertIn("absolute path disclosure", result["blockers"])


if __name__ == "__main__":
    unittest.main()
