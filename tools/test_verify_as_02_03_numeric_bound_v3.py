from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_as_02_03_numeric_bound_v3 as verifier


class BoundV3MutationTests(unittest.TestCase):
    def test_historical_manifests_are_valid_from_immutable_candidate_identity(self):
        for path in verifier.MANIFESTS.values():
            result = verifier.verify(path)
            self.assertTrue(result["valid"], result)
            self.assertEqual(result["harness_binding"], "historical_candidate_commit")

    def test_wrapper_policy_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-02"].read_text(encoding="utf-8"))
        report_item = document["reports"][0]
        report_path = verifier.ROOT / report_item["path"]
        mutated_path = verifier.ROOT / "docs/baselines/as-02-wrapper-policy-mutation.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["wrapper_policy"]["rustc_wrapper"] = "inherited"
        mutated_path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        try:
            report_item["path"] = "docs/baselines/as-02-wrapper-policy-mutation.json"
            report_item["sha256"] = verifier.sha(mutated_path)
            result = verifier.verify(verifier.MANIFESTS["AS-02"], document=document)
            self.assertFalse(result["valid"])
            self.assertIn("wrapper policy", result["blockers"])
        finally:
            mutated_path.unlink(missing_ok=True)

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

    def test_fixture_binding_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-02"].read_text(encoding="utf-8"))
        document["fixture_sha256"] = "0" * 64
        self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-02"], document=document)["valid"])

    def test_aggregate_binding_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-03"].read_text(encoding="utf-8"))
        document["aggregate"]["sha256"] = "0" * 64
        self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-03"], document=document)["valid"])

    def test_toolchain_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-02"].read_text(encoding="utf-8"))
        original = verifier.ROOT / document["reports"][0]["path"]
        mutated_path = verifier.ROOT / "docs/baselines/as-02-toolchain-mutation.json"
        report = json.loads(original.read_text(encoding="utf-8"))
        report["toolchain"]["cargo"]["version_sha256"] = "0" * 64
        mutated_path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        try:
            document["reports"][0]["path"] = "docs/baselines/as-02-toolchain-mutation.json"
            document["reports"][0]["sha256"] = verifier.sha(mutated_path)
            result = verifier.verify(verifier.MANIFESTS["AS-02"], document=document)
            self.assertFalse(result["valid"])
            self.assertIn("toolchain schema", result["blockers"])
        finally:
            mutated_path.unlink(missing_ok=True)

    def test_nonce_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-03"].read_text(encoding="utf-8"))
        original = verifier.ROOT / document["reports"][0]["path"]
        mutated_path = verifier.ROOT / "docs/baselines/as-03-nonce-mutation.json"
        report = json.loads(original.read_text(encoding="utf-8"))
        report["fresh_run_nonce"] = "not-a-64-hex-nonce"
        mutated_path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        try:
            document["reports"][0]["path"] = "docs/baselines/as-03-nonce-mutation.json"
            document["reports"][0]["sha256"] = verifier.sha(mutated_path)
            result = verifier.verify(verifier.MANIFESTS["AS-03"], document=document)
            self.assertFalse(result["valid"])
            self.assertIn("run identity", result["blockers"])
        finally:
            mutated_path.unlink(missing_ok=True)

    def test_resolved_path_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-02"].read_text(encoding="utf-8"))
        original = verifier.ROOT / document["reports"][0]["path"]
        mutated_path = verifier.ROOT / "docs/baselines/as-02-resolved-path-mutation.json"
        report = json.loads(original.read_text(encoding="utf-8"))
        report["execution"]["candidate"]["resolved_path"] = "C:/outside/binary"
        mutated_path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        try:
            document["reports"][0]["path"] = "docs/baselines/as-02-resolved-path-mutation.json"
            document["reports"][0]["sha256"] = verifier.sha(mutated_path)
            self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-02"], document=document)["valid"])
        finally:
            mutated_path.unlink(missing_ok=True)

    def test_nested_nan_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-02"].read_text(encoding="utf-8"))
        original = verifier.ROOT / document["reports"][0]["path"]
        mutated_path = verifier.ROOT / "docs/baselines/as-02-nested-nan-mutation.json"
        report = json.loads(original.read_text(encoding="utf-8"))
        report["metrics"]["candidate_snapshot"]["blocks"][0]["gate"]["full_band_rms"] = float("nan")
        mutated_path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        try:
            document["reports"][0]["path"] = "docs/baselines/as-02-nested-nan-mutation.json"
            document["reports"][0]["sha256"] = verifier.sha(mutated_path)
            self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-02"], document=document)["valid"])
        finally:
            mutated_path.unlink(missing_ok=True)

    def test_audit_stale_mutation_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-03"].read_text(encoding="utf-8"))
        document["audit"]["sha256"] = "0" * 64
        self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-03"], document=document)["valid"])

    def test_aggregator_reproducibility_binding_is_rejected(self):
        document = yaml.safe_load(verifier.MANIFESTS["AS-02"].read_text(encoding="utf-8"))
        document["harness"]["aggregator"]["sha256"] = "0" * 64
        self.assertFalse(verifier.verify(verifier.MANIFESTS["AS-02"], document=document)["valid"])


if __name__ == "__main__":
    unittest.main()
