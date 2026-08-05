from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from verify_m1_rule_ledger import _snapshot_matches, _source_repositories


class ExternalSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.authority = json.loads((ROOT / "schemas" / "authority.v1.yaml").read_text(encoding="utf-8"))
        self.contract = next(
            contract
            for contract in self.authority["external_contracts"]
            if contract["identifier"]["value"] == "pybert.simulation.v1"
        )
        self.repositories = _source_repositories(self.authority)
        repository = self.repositories["py-bert-agent"]
        self.evidence = {
            "source_snapshot": {
                "repository": "py-bert-agent",
                "revision": repository["head"],
                "tree": repository["tree"],
            }
        }

    def test_external_snapshot_requires_authority_pinned_head_and_tree(self):
        self.assertTrue(_snapshot_matches(self.evidence, self.contract, self.repositories))
        wrong_revision = {"source_snapshot": {**self.evidence["source_snapshot"], "revision": "0" * 40}}
        wrong_tree = {"source_snapshot": {**self.evidence["source_snapshot"], "tree": "0" * 40}}
        self.assertFalse(_snapshot_matches(wrong_revision, self.contract, self.repositories))
        self.assertFalse(_snapshot_matches(wrong_tree, self.contract, self.repositories))

    def test_external_snapshot_rejects_unknown_repository(self):
        missing_repository = {"source_snapshot": {**self.evidence["source_snapshot"], "repository": "missing"}}
        self.assertFalse(_snapshot_matches(missing_repository, self.contract, self.repositories))


if __name__ == "__main__":
    unittest.main()
