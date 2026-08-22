import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_as_01_fit_sparam_bound as verifier


class VerifyAs01FitSparamBoundTests(unittest.TestCase):
    def setUp(self):
        self.manifest = yaml.safe_load(verifier.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        self.report = json.loads((verifier.ROOT / verifier.REPORTS[0][0]).read_text(encoding="utf-8"))

    def reject_manifest(self, document):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with self.assertRaises(verifier.VerificationError):
                verifier.verify(path)

    def reject_report(self, document):
        _, _, run_id, nonce = verifier.REPORTS[0]
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_report(document, run_id=run_id, nonce=nonce)

    def test_valid(self):
        result = verifier.verify()
        self.assertEqual(result["status"], "completed_numeric_mismatch")
        self.assertTrue(result["numeric_mismatch_open"])

    def test_status_overclaim_rejected(self):
        mutated = copy.deepcopy(self.manifest)
        mutated["status"] = "accepted"
        self.reject_manifest(mutated)

    def test_candidate_tree_mutation_rejected(self):
        mutated = copy.deepcopy(self.manifest)
        mutated["sources"]["candidate"]["tree"] = "0" * 40
        self.reject_manifest(mutated)

    def test_lock_mutation_rejected(self):
        mutated = copy.deepcopy(self.manifest)
        mutated["harness"]["oracle_lock"]["sha256"] = "0" * 64
        self.reject_manifest(mutated)

    def test_report_nonce_mutation_rejected(self):
        mutated = copy.deepcopy(self.report)
        mutated["fresh_run_nonce"] = "0" * 64
        self.reject_report(mutated)

    def test_report_extra_top_level_key_rejected(self):
        mutated = copy.deepcopy(self.report)
        mutated["absolute_workdir"] = r"C:\Users\runner\repo"
        self.reject_report(mutated)

    def test_binary_digest_mutation_rejected(self):
        mutated = copy.deepcopy(self.report)
        mutated["build"]["binary_sha256"] = "0" * 64
        self.reject_report(mutated)

    def test_numeric_scalar_mutation_rejected(self):
        mutated = copy.deepcopy(self.report)
        scenario = next(row for row in mutated["comparison"]["scenarios"] if row["id"] == "full_band_defaults")
        scenario["candidate_summary"]["rms_error"] += 1e-9
        self.reject_report(mutated)

    def test_touchstone_digest_mutation_rejected(self):
        mutated = copy.deepcopy(self.report)
        scenario = next(row for row in mutated["comparison"]["scenarios"] if row["id"] == "full_band_defaults")
        scenario["candidate_fitted_touchstone"]["logical_sha256"] = "0" * 64
        self.reject_report(mutated)

    def test_duplicate_scenario_promoted_rejected(self):
        mutated = copy.deepcopy(self.report)
        scenario = next(row for row in mutated["comparison"]["scenarios"] if row["id"] == "target_failure_and_success")
        scenario["coverage_note"] = None
        self.reject_report(mutated)

    def test_parity_claim_rejected(self):
        mutated = copy.deepcopy(self.report)
        mutated["parity_claim"] = True
        self.reject_report(mutated)

    def test_manifest_report_hash_mutation_rejected(self):
        mutated = copy.deepcopy(self.manifest)
        mutated["formal_reports"][0]["sha256"] = "0" * 64
        self.reject_manifest(mutated)

    def test_manifest_semantic_scalar_mutation_rejected(self):
        mutated = copy.deepcopy(self.manifest)
        mutated["semantic_observation"]["common_leaf"]["candidate_report_rms"] += 1e-9
        self.reject_manifest(mutated)

    def test_aggregate_hash_mutation_rejected(self):
        mutated = copy.deepcopy(self.manifest)
        mutated["aggregate"]["sha256"] = "0" * 64
        self.reject_manifest(mutated)

    def test_audit_hash_mutation_rejected(self):
        mutated = copy.deepcopy(self.manifest)
        mutated["audit"]["sha256"] = "0" * 64
        self.reject_manifest(mutated)

    def test_supersession_overclaim_rejected(self):
        mutated = copy.deepcopy(self.manifest)
        mutated["supersession"]["does_not_supersede_open_migration_or_non_parity_claims"] = False
        self.reject_manifest(mutated)


if __name__ == "__main__":
    unittest.main()
