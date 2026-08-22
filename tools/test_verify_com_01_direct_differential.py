import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_com_01_direct_differential import DEFAULT_REPORT, VerificationError, verify


class Com01DifferentialEvidenceTests(unittest.TestCase):
    def setUp(self):
        if not DEFAULT_REPORT.is_file():
            self.skipTest("formal external-fixture report is not generated in this checkout")
        self.document = json.loads(DEFAULT_REPORT.read_text(encoding="utf-8"))

    def mutate_fails(self, mutate):
        document = copy.deepcopy(self.document)
        mutate(document)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify(path)

    def test_current_report(self):
        result = verify()
        self.assertEqual(result["run_count"], 2)
        self.assertEqual(result["scenario_count"], 14)

    def test_source_mutation_fails(self):
        self.mutate_fails(lambda report: report["source"].__setitem__("commit", "0" * 40))

    def test_nonce_mutation_fails(self):
        self.mutate_fails(lambda report: report["runs"][1].__setitem__("nonce", report["runs"][0]["nonce"]))

    def test_fixture_digest_mutation_fails(self):
        self.mutate_fails(lambda report: report["fixtures"][0].__setitem__("sha256", "0" * 64))

    def test_scenario_deletion_fails(self):
        self.mutate_fails(lambda report: report["runs"][0]["scenarios"].pop())

    def test_path_disclosure_fails(self):
        self.mutate_fails(lambda report: report["candidate"].__setitem__("executable", "C:\\Users\\runner\\candidate.exe"))

    def test_raw_materialized_payload_fails(self):
        self.mutate_fails(
            lambda report: report["runs"][0]["scenarios"][2]["oracle_summary"].__setitem__(
                "raw_parameters", {"f_b": 53.125e9}
            )
        )

    def test_error_category_drift_cannot_be_reported_as_match(self):
        def mutate(report):
            item = next(
                scenario
                for scenario in report["runs"][0]["scenarios"]
                if scenario["comparison"] == "error_code_match"
            )
            item["candidate_error_category"] = "different_error"

        self.mutate_fails(mutate)

    def test_fingerprint_only_drift_requires_empty_difference_keys(self):
        def mutate(report):
            item = next(
                scenario
                for scenario in report["runs"][0]["scenarios"]
                if scenario["comparison"] == "values_equal_fingerprint_drift"
            )
            item["difference_keys"] = ["materialized.parameters.secret"]

        self.mutate_fails(mutate)


if __name__ == "__main__":
    unittest.main()
