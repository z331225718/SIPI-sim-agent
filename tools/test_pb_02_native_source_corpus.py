"""Mutation tests for the PB-02 pinned-native-source corpus evidence gate."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

try:  # pragma: no cover - direct execution uses the fallback
    from . import run_pb_02_native_source_corpus as runner
    from . import verify_pb_02_native_source_corpus as verifier
except ImportError:  # pragma: no cover
    import run_pb_02_native_source_corpus as runner
    import verify_pb_02_native_source_corpus as verifier


HEX40 = "a" * 40
HEX64 = "b" * 64


def process(exit_code: int) -> dict[str, object]:
    return {"exit_code": exit_code, "stdout": {}, "stderr": {}}


def success(case_id: str) -> dict[str, object]:
    return {
        "id": case_id,
        "input": {"bytes": 1, "sha256": HEX64, "file": {}},
        "candidate_process": process(0),
        "oracle_process": process(0),
        "kind": "complete_native_artifact",
        "comparison": {
            "metadata": {"passed": True, "drifts": [], "excluded_paths": list(runner.METADATA_EXCLUSIONS)},
            "arrays": {"passed": True, "drifts": [], "members": [{"name": "x.npy", "present": True, "passed": True}]},
            "artifacts": {
                "candidate": {"meta": {"bytes": 1, "sha256": HEX64}, "arrays": {"bytes": 1, "sha256": HEX64}},
                "oracle": {"meta": {"bytes": 1, "sha256": HEX64}, "arrays": {"bytes": 1, "sha256": HEX64}},
            },
        },
        "passed": True,
    }


def rejection() -> dict[str, object]:
    return {
        "id": runner.REJECTION_CASE,
        "input": {"bytes": 1, "sha256": HEX64, "file": {}},
        "candidate_process": process(1),
        "oracle_process": process(1),
        "kind": "expected_rejection",
        "error_category": "additive_noise_length_mismatch",
        "no_artifacts": {"candidate": True, "oracle": True},
        "passed": True,
    }


def report(run_id: str, nonce: str) -> dict[str, object]:
    toolchain = {role: {"role": role, "executable": f"{role}.exe", "file_sha256": HEX64, "version_sha256": HEX64, "version_exit": 0, "path_redacted": True} for role in ("cargo", "rustc", "uv", "link")}
    return {
        "schema": runner.SCHEMA,
        "version": 1,
        "run_id": run_id,
        "nonce": nonce,
        "status": "passed",
        "scope": {"source_test_path": runner.SOURCE_TEST_PATH, "source_test_blob": runner.SOURCE_TEST_BLOB, "successful_case_ids": list(runner.SUCCESS_CASES), "rejection_case_id": runner.REJECTION_CASE, "numeric_rtol": runner.NUMERIC_RTOL, "numeric_atol": runner.NUMERIC_ATOL, "metadata_exclusions": list(runner.METADATA_EXCLUSIONS)},
        "candidate": {"commit": HEX40, "tree": HEX40, "archive_sha256": HEX64, "fixture": {"path": runner.FIXTURE, "bytes": 1, "sha256": HEX64}},
        "upstream": {"commit": runner.PINNED_UPSTREAM, "tree": runner.PINNED_UPSTREAM_TREE, "archive_sha256": HEX64},
        "toolchain": toolchain,
        "build": {},
        "oracle_runtime": {},
        "cases": [*(success(case_id) for case_id in runner.SUCCESS_CASES), rejection()],
    }


class CorpusGateTests(unittest.TestCase):
    def write(self, root: Path, name: str, value: dict[str, object]) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_valid_reports_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.write(root, "first.json", report("run-01", "1" * 64))
            second = self.write(root, "second.json", report("run-02", "2" * 64))
            result = verifier.aggregate([first, second], root / "aggregate.json")
            self.assertEqual(result["status"], "passed")

    def test_missing_source_case_is_rejected(self) -> None:
        value = report("run-01", "1" * 64)
        value["cases"].pop()  # type: ignore[index]
        with self.assertRaisesRegex(verifier.VerifyError, "case count"):
            verifier._validate_report(value)

    def test_exclusion_expansion_is_rejected(self) -> None:
        value = report("run-01", "1" * 64)
        value["cases"][0]["comparison"]["metadata"]["excluded_paths"].append("$.extra")  # type: ignore[index]
        with self.assertRaisesRegex(verifier.VerifyError, "metadata acceptance"):
            verifier._validate_report(value)

    def test_duplicate_nonce_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.write(root, "first.json", report("run-01", "1" * 64))
            second = self.write(root, "second.json", report("run-02", "1" * 64))
            with self.assertRaisesRegex(verifier.VerifyError, "distinct run IDs and nonces"):
                verifier.aggregate([first, second], root / "aggregate.json")


if __name__ == "__main__":
    unittest.main()
