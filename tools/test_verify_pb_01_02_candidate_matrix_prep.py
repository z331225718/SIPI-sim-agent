"""Synthetic baseline and coordination-mutation tests for the PB prep gate."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

try:
    from .verify_pb_01_02_candidate_matrix_prep import (
        EXPECTED_PARENT,
        MANIFEST_PATH,
        VerifyError,
        load_manifest,
        validate_future_report_header,
        verify,
    )
except ImportError:  # pragma: no cover - direct unittest execution
    from verify_pb_01_02_candidate_matrix_prep import (  # type: ignore[no-redef]
        EXPECTED_PARENT,
        MANIFEST_PATH,
        VerifyError,
        load_manifest,
        validate_future_report_header,
        verify,
    )


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path(r"C:\Users\z3312\code\Py-bert-agent")


class CandidateMatrixPrepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest(MANIFEST_PATH)

    def test_complete_synthetic_baseline(self) -> None:
        result = verify(copy.deepcopy(self.manifest), ROOT, require_sources=False)
        self.assertTrue(result["valid"], result)

    def test_live_archive_and_fixture_baseline(self) -> None:
        result = verify(copy.deepcopy(self.manifest), ROOT, UPSTREAM, require_sources=True)
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["formal_record_absent"])

    def test_candidate_archive_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["candidate"]["archive_sha256"] = "1" * 64
        result = verify(document, ROOT, UPSTREAM, require_sources=True)
        self.assertFalse(result["valid"])

    def test_fixture_provenance_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["fixtures"]["PB-02"]["sha256"] = "2" * 64
        result = verify(document, ROOT, UPSTREAM, require_sources=True)
        self.assertFalse(result["valid"])

    def test_interposed_checkpoint_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["interposed_checkpoint"]["to_tree"] = "5" * 40
        result = verify(document, ROOT, UPSTREAM, require_sources=True)
        self.assertFalse(result["valid"])

    def test_derived_input_crossfield_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["cases"][0]["derived_bytes"] += 1
        result = verify(document, ROOT, UPSTREAM, require_sources=True)
        self.assertFalse(result["valid"])

    def test_case_blocker_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["cases"][1]["diagnostic_blockers"] = []
        result = verify(document, ROOT, require_sources=False)
        self.assertFalse(result["valid"])

    def test_strict_comparator_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["comparator_policy"]["PB-02"]["metadata_drop_allowed"] = True
        result = verify(document, ROOT, require_sources=False)
        self.assertFalse(result["valid"])

    def test_nested_unknown_key_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["toolchain"]["roles"]["cargo"]["unexpected"] = True
        result = verify(document, ROOT, require_sources=False)
        self.assertFalse(result["valid"])

    def test_nonfinite_manifest_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["toolchain"]["timeout_seconds"] = float("nan")
        result = verify(document, ROOT, require_sources=False)
        self.assertFalse(result["valid"])

    def test_duplicate_manifest_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.yaml"
            path.write_text("schema: first\nschema: second\n", encoding="utf-8")
            with self.assertRaises(VerifyError):
                load_manifest(path)

    def test_toolchain_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["toolchain"]["roles"]["cargo"]["version_sha256"] = "3" * 64
        result = verify(document, ROOT, require_sources=True)
        self.assertFalse(result["valid"])

    def test_formal_path_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.manifest)
        document["future_replay"]["formal_paths"].append("docs/formal.json")
        result = verify(document, ROOT, require_sources=False)
        self.assertFalse(result["valid"])

    def test_runner_challenge_baseline_and_run_id_mutation(self) -> None:
        for run_id, index in (("pb-01-02-candidate-run-01", 1), ("pb-01-02-candidate-run-02", 2)):
            report = {
                "schema": "sipi.pb-01-02-candidate-matrix-replay.v1",
                "version": 1,
                "status": "scoped_matrix_blocked",
                "run_id": run_id,
                "challenge": {
                    "id": "pb-01-02-candidate-matrix-v1", "run_index": index, "run_count": 2,
                    "fresh_archive_replay": True, "nonce_required": True, "report_sha256_required": True,
                },
                "fresh_run_nonce": "4" * 64,
                **{key: {} for key in ("candidate", "upstream", "corpus", "fixtures", "toolchain", "custody", "cases", "claims")},
            }
            self.assertEqual(validate_future_report_header(report)["run_id"], run_id)
            broken = copy.deepcopy(report)
            broken["challenge"]["run_index"] = 2 if index == 1 else 1
            with self.assertRaises(RuntimeError):
                validate_future_report_header(broken)
        broken_id = copy.deepcopy(report)
        broken_id["run_id"] = "diagnostic-run"
        with self.assertRaises(RuntimeError):
            validate_future_report_header(broken_id)

    def test_nonce_mutation_is_rejected(self) -> None:
        report = {
            "schema": "sipi.pb-01-02-candidate-matrix-replay.v1", "version": 1,
            "status": "scoped_matrix_blocked", "run_id": "pb-01-02-candidate-run-01",
            "challenge": {"id": "pb-01-02-candidate-matrix-v1", "run_index": 1, "run_count": 2, "fresh_archive_replay": True, "nonce_required": True, "report_sha256_required": True},
            "fresh_run_nonce": "not-a-nonce",
            **{key: {} for key in ("candidate", "upstream", "corpus", "fixtures", "toolchain", "custody", "cases", "claims")},
        }
        with self.assertRaises(RuntimeError):
            validate_future_report_header(report)

    def test_prep_commit_is_required_for_live_gate(self) -> None:
        result = verify(copy.deepcopy(self.manifest), ROOT, require_sources=False, require_prep_commit=True)
        self.assertFalse(result["valid"])

    def test_non_prep_parent_is_rejected(self) -> None:
        result = verify(copy.deepcopy(self.manifest), ROOT, prep_commit=EXPECTED_PARENT, require_sources=False)
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
