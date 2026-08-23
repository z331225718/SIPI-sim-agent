"""Mutation tests for PB-04/PB-05 external-reference fail-closed gates."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_pb_04_05_python_external as verifier  # noqa: E402


class VerifyPbExternalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row = "PB-04"
        path = verifier.ROOT / verifier.ROWS[self.row]["one"]
        self.report = json.loads(path.read_text(encoding="utf-8"))

    def _errors(self, report: dict) -> list[str]:
        errors: list[str] = []
        verifier.verify_report(self.row, report, errors, "mutated")
        return errors

    def test_overlay_source_mode_is_rejected(self) -> None:
        report = copy.deepcopy(self.report)
        report["source_mode"] = "git_archive_plus_lane_working_tree_content_addressed"
        self.assertTrue(self._errors(report))

    def test_candidate_overlay_claim_is_rejected(self) -> None:
        report = copy.deepcopy(self.report)
        report["candidate"]["working_tree_overlay"] = {"crates/x.rs": "0" * 64}
        self.assertTrue(self._errors(report))

    def test_python_selection_substitution_is_rejected(self) -> None:
        report = copy.deepcopy(self.report)
        report["selection"]["implementation"] = "rust_portable_reference"
        self.assertTrue(self._errors(report))

    def test_self_compare_claim_is_rejected(self) -> None:
        report = copy.deepcopy(self.report)
        report["claims"]["same_crate_self_compare"] = True
        self.assertTrue(self._errors(report))

    def test_reference_schema_and_2d_eye_contract_are_required(self) -> None:
        report = copy.deepcopy(self.report)
        report["oracle"]["reference"]["result_adapter_schema"] = "wrong"
        report["oracle"]["reference"]["two_dimensional_arrays"] = []
        errors = self._errors(report)
        self.assertGreaterEqual(len(errors), 2)

    def test_pb05_not_evaluated_requires_external_reference(self) -> None:
        row = "PB-05"
        path = verifier.ROOT / verifier.ROWS[row]["one"]
        report = json.loads(path.read_text(encoding="utf-8"))
        report["comparison"]["reference_required"] = "same_crate_shadow"
        errors: list[str] = []
        verifier.verify_report(row, report, errors, "mutated")
        self.assertTrue(errors)

    def test_exact_archive_identity_is_required(self) -> None:
        report = copy.deepcopy(self.report)
        report["candidate"]["archive_sha256"] = "0" * 64
        self.assertTrue(self._errors(report))

    def test_toolchain_allowed_keys_are_strict(self) -> None:
        report = copy.deepcopy(self.report)
        report["toolchain"]["unexpected"] = True
        self.assertTrue(self._errors(report))

    def test_harness_keys_and_snapshot_are_strict(self) -> None:
        report = copy.deepcopy(self.report)
        report["harness"]["unexpected"] = {"path": "tools/x.py", "sha256": "0" * 64}
        self.assertTrue(self._errors(report))

        report = copy.deepcopy(self.report)
        report["harness"]["python_external_reference"]["snapshot"] = "working_tree"
        self.assertTrue(self._errors(report))

    def test_binary_binding_mutation_is_rejected(self) -> None:
        report = copy.deepcopy(self.report)
        report["build"]["binary_sha256"] = "0" * 64
        self.assertTrue(self._errors(report))

    def test_manifest_report_and_audit_bindings_are_loaded(self) -> None:
        for row in ("PB-04", "PB-05"):
            manifest_path = verifier.ROOT / verifier.MANIFESTS[row]
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            report_paths = [verifier.ROOT / verifier.ROWS[row][key] for key in ("one", "two")]
            reports = [json.loads(path.read_text(encoding="utf-8")) for path in report_paths]
            bindings = [
                {
                    "path": verifier.ROWS[row][key],
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "run_id": report["run_id"],
                    "fresh_run_nonce": report["fresh_run_nonce"],
                }
                for key, path, report in zip(("one", "two"), report_paths, reports)
            ]
            aggregate_path = verifier.ROOT / verifier.ROWS[row]["aggregate"]
            aggregate_sha = hashlib.sha256(aggregate_path.read_bytes()).hexdigest()
            audit_sha = hashlib.sha256((verifier.ROOT / verifier.AUDITS[row]).read_bytes()).hexdigest()
            manifest["evidence"]["reports"][0]["sha256"] = "0" * 64
            errors: list[str] = []
            verifier.verify_manifest(row, manifest, "0" * 64, reports, bindings, aggregate_sha, audit_sha, errors, verifier.ROOT)
            self.assertTrue(errors, row)


if __name__ == "__main__":
    unittest.main()
