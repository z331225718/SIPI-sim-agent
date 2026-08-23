from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_as_02_03_numeric_bound_v3 as verifier


class BoundV3MutationTests(unittest.TestCase):
    def test_manifests_are_pending_until_post_prep_replay(self):
        for path in verifier.MANIFESTS.values():
            result = verifier.verify(path)
            self.assertIn("report", " ".join(result["blockers"]))

    def test_wrapper_policy_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-02"].read_text(encoding="utf-8"))
        document["reports"] = []
        document["wrapper_policy"] = {"rustc_wrapper": "inherited"}
        self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-02"], document=document)["valid"])

    def test_source_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-02"].read_text(encoding="utf-8"))
        document["source"]["candidate"]["tree"] = "0" * 40
        self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-02"], document=document)["valid"])

    def test_path_escape_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-03"].read_text(encoding="utf-8"))
        document["reports"][0]["path"] = "docs/../escape.json"
        self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-03"], document=document)["valid"])

    def test_global_close_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-03"].read_text(encoding="utf-8"))
        document["global_row_closed"] = True
        self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-03"], document=document)["valid"])


if __name__ == "__main__":
    unittest.main()
