"""Mutation checks for immutable AS-02..AS-06 v2 manifests."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_as_remaining_bound as verifier  # noqa: E402


MANIFESTS = [
    ROOT / "docs/baselines/as-02-fit-sparam-cascade-direct-port.v2.yaml",
    ROOT / "docs/baselines/as-03-fit-yparam-direct-port.v2.yaml",
    ROOT / "docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml",
    ROOT / "docs/baselines/as-05-run-hspice-rust-control-direct-port.v2.yaml",
    ROOT / "docs/baselines/as-06-run-rfm-direct-port.v2.yaml",
]


class VerifyImmutableAsEvidenceTests(unittest.TestCase):
    def reject(self, document, path):
        result = verifier.verify(document, path)
        self.assertFalse(result["valid"], result)

    def test_manifests_are_valid(self):
        for path in MANIFESTS:
            with self.subTest(path=path.name):
                result = verifier.verify(yaml.safe_load(path.read_text(encoding="utf-8")), path)
                self.assertTrue(result["valid"], result)

    def test_candidate_binding_mutation_is_rejected(self):
        for path in MANIFESTS:
            document = copy.deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
            document["source"]["candidate"]["tree"] = "0" * 40
            self.reject(document, path)

    def test_report_hash_mutation_is_rejected(self):
        for path in MANIFESTS:
            document = copy.deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
            document["reports"][0]["sha256"] = "0" * 64
            self.reject(document, path)

    def test_parity_overclaim_is_rejected(self):
        for path in MANIFESTS:
            document = copy.deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
            document["status"] = "accepted_numeric_parity"
            self.reject(document, path)

    def test_audit_hash_mutation_is_rejected(self):
        for path in MANIFESTS:
            document = copy.deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
            document["audit"]["sha256"] = "0" * 64
            self.reject(document, path)

    def test_helper_drift_is_rejected(self):
        for path in MANIFESTS:
            document = copy.deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
            document["harness"]["helper"]["sha256"] = "0" * 64
            self.reject(document, path)

    def test_repo_relative_path_escape_is_rejected(self):
        for path in MANIFESTS:
            document = copy.deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
            document["reports"][0]["path"] = "../outside.json"
            self.reject(document, path)

    def test_cross_file_toolchain_drift_is_rejected(self):
        for path in MANIFESTS:
            document = copy.deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
            document["fixture"]["input_tree_sha256"][1] = "0" * 64
            self.reject(document, path)

    def test_manifest_toolchain_drift_is_rejected(self):
        for path in MANIFESTS:
            document = copy.deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
            document["toolchain"]["cargo"]["file_sha256"] = "0" * 64
            self.reject(document, path)


if __name__ == "__main__":
    unittest.main()
