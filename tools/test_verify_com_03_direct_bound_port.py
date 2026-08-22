import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from aggregate_com_03_direct_oracle import BOUND_INPUT_SCHEMA, BOUND_SCHEMA, aggregate
from verify_com_03_direct_bound_port import DEFAULT_MANIFEST, ROOT, VerificationError, verify


class Com03DirectBoundVerifierTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load(DEFAULT_MANIFEST.read_text(encoding="utf-8"))

    def mutate_fails(self, mutate):
        document = copy.deepcopy(self.document)
        mutate(document)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify(path)

    def aggregate_fails(self, first, second):
        with self.assertRaises(ValueError):
            aggregate(first, second, input_schema=BOUND_INPUT_SCHEMA, aggregate_schema=BOUND_SCHEMA)

    def test_current_manifest(self):
        result = verify()
        self.assertEqual(result["scenario_count"], 23)
        self.assertEqual(result["fresh_runs"], 2)
        self.assertFalse(result["rebuild_checked"])

    def test_candidate_commit_mutation_fails(self):
        self.mutate_fails(lambda document: document["candidate"].__setitem__("commit", "0" * 40))

    def test_candidate_tree_mutation_fails(self):
        self.mutate_fails(lambda document: document["candidate"].__setitem__("tree", "0" * 40))

    def test_audit_path_mutation_fails(self):
        self.mutate_fails(lambda document: document["audit"].__setitem__("path", "../outside-audit.md"))

    def test_audit_hash_mutation_fails(self):
        self.mutate_fails(lambda document: document["audit"].__setitem__("sha256", "0" * 64))

    def test_audit_content_mutation_fails(self):
        document = copy.deepcopy(self.document)
        audit_source = ROOT / document["audit"]["path"]
        with tempfile.TemporaryDirectory(dir=ROOT / "docs") as directory:
            mutated_audit = Path(directory) / "audit.md"
            mutated_audit.write_bytes(audit_source.read_bytes() + b"\nmutation\n")
            document["audit"]["path"] = mutated_audit.relative_to(ROOT).as_posix()
            with tempfile.TemporaryDirectory() as manifest_directory:
                manifest = Path(manifest_directory) / "manifest.yaml"
                manifest.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
                with self.assertRaises(VerificationError):
                    verify(manifest)

    def test_candidate_binary_mutation_fails(self):
        self.mutate_fails(lambda document: document["candidate"].__setitem__("binary_sha256", "0" * 64))

    def test_report_hash_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"]["invocations"][0].__setitem__("sha256", "0" * 64))

    def test_duplicate_report_path_mutation_fails(self):
        self.mutate_fails(
            lambda document: document["oracle"]["invocations"][1].__setitem__(
                "report", document["oracle"]["invocations"][0]["report"]
            )
        )

    def test_duplicate_run_id_mutation_fails(self):
        self.mutate_fails(
            lambda document: document["oracle"]["invocations"][1].__setitem__(
                "run_id", document["oracle"]["invocations"][0]["run_id"]
            )
        )

    def test_duplicate_nonce_mutation_fails(self):
        self.mutate_fails(
            lambda document: document["oracle"]["invocations"][1].__setitem__(
                "fresh_run_nonce", document["oracle"]["invocations"][0]["fresh_run_nonce"]
            )
        )

    def test_aggregate_hash_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"].__setitem__("aggregate_sha256", "0" * 64))

    def test_scenario_digest_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"].__setitem__("scenario_set_sha256", "0" * 64))

    def test_bound_mode_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"].__setitem__("bound_mode", "caller_binary"))

    def test_nonclaim_mutation_fails(self):
        self.mutate_fails(lambda document: document.__setitem__("status", "release_ready"))

    def test_reports_redact_local_paths(self):
        for report in DEFAULT_MANIFEST.parent.glob("com-03-direct-port-bound-oracle*.json"):
            text = report.read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users\\", text)
            self.assertNotIn("\\Temp\\", text)
            self.assertNotIn("/tmp/", text)

    def test_aggregate_rejects_duplicate_path(self):
        report = DEFAULT_MANIFEST.parent / "com-03-direct-port-bound-oracle.v2.json"
        self.aggregate_fails(report, report)

    def test_aggregate_rejects_duplicate_report_digest(self):
        report = DEFAULT_MANIFEST.parent / "com-03-direct-port-bound-oracle.v2.json"
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_bytes(report.read_bytes())
            self.aggregate_fails(report, duplicate)

    def test_aggregate_rejects_duplicate_run_id(self):
        first = DEFAULT_MANIFEST.parent / "com-03-direct-port-bound-oracle.v2.json"
        second = DEFAULT_MANIFEST.parent / "com-03-direct-port-bound-oracle-run2.v2.json"
        document = json.loads(second.read_text(encoding="utf-8"))
        document["run_id"] = json.loads(first.read_text(encoding="utf-8"))["run_id"]
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / "same-run-id.json"
            mutated.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
            self.aggregate_fails(first, mutated)

    def test_aggregate_rejects_duplicate_nonce(self):
        first = DEFAULT_MANIFEST.parent / "com-03-direct-port-bound-oracle.v2.json"
        second = DEFAULT_MANIFEST.parent / "com-03-direct-port-bound-oracle-run2.v2.json"
        document = json.loads(second.read_text(encoding="utf-8"))
        document["fresh_run_nonce"] = json.loads(first.read_text(encoding="utf-8"))["fresh_run_nonce"]
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / "same-nonce.json"
            mutated.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
            self.aggregate_fails(first, mutated)


if __name__ == "__main__":
    unittest.main()
