import copy
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from run_com_03_direct_oracle import git, run
from verify_com_03_direct_port import DEFAULT_MANIFEST, VerificationError, verify


class Com03DirectPortVerifierTests(unittest.TestCase):
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

    def test_current_manifest(self):
        result = verify()
        self.assertEqual(result["source_paths"], 3)
        self.assertEqual(result["fresh_runs"], 2)
        self.assertEqual(result["scenario_count"], 23)

    def test_bound_mode_rejects_external_binary(self):
        repository = Path(__file__).resolve().parents[1]
        candidate_commit = git(repository, "rev-parse", "HEAD")
        with self.assertRaisesRegex(RuntimeError, "forbidden"):
            run(
                upstream_root=Path(r"C:\Users\z3312\code\COM"),
                rust_binary=Path(r"C:\external\arbitrary.exe"),
                run_id="bound-reject-test",
                candidate_root=repository,
                candidate_commit=candidate_commit,
                toolchain="test-toolchain",
            )

    def test_reports_redact_local_paths(self):
        report_root = DEFAULT_MANIFEST.parent
        for report in (
            report_root / "com-03-direct-port-oracle.v1.json",
            report_root / "com-03-direct-port-oracle-run2.v1.json",
            report_root / "com-03-direct-port-oracle-aggregate.v1.json",
        ):
            text = report.read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users\\", text)
            self.assertNotIn("\\Temp\\", text)
            self.assertNotIn("/tmp/", text)

    def test_commit_mutation_fails(self):
        self.mutate_fails(lambda document: document["source"].__setitem__("commit", "0" * 40))

    def test_license_mutation_fails(self):
        self.mutate_fails(lambda document: document["source"]["source_paths"][0].__setitem__("license", "BSD-3-Clause"))

    def test_status_mutation_fails(self):
        self.mutate_fails(lambda document: document.__setitem__("status", "parity_pending"))

    def test_report_hash_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"]["invocations"][0].__setitem__("sha256", "0" * 64))

    def test_scenario_matrix_mutation_fails(self):
        self.mutate_fails(lambda document: document.__setitem__("oracle", {**document["oracle"], "scenario_count": 18}))

    def test_stderr_policy_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"].__setitem__("stderr_diagnostic_text", "exact"))

    def test_candidate_binding_status_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"].__setitem__("candidate_binding_status", "immutable_candidate_bound"))

    def test_scenario_set_digest_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"].__setitem__("scenario_set_sha256", "0" * 64))

    def test_archive_inventory_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"].__setitem__("upstream_archive_inventory_sha256", "0" * 64))

    def test_bound_execution_policy_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"].__setitem__("bound_mode", "caller_binary"))

    def test_report_path_policy_mutation_fails(self):
        self.mutate_fails(lambda document: document["oracle"].__setitem__("report_path_policy", "absolute"))

    def test_nonclaim_mutation_fails(self):
        self.mutate_fails(lambda document: document.__setitem__("non_claims", ["no_product_capability_promotion"]))


if __name__ == "__main__":
    unittest.main()
