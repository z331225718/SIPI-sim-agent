"""Focused tests for immutable COM-01 replay orchestration."""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))

from aggregate_com_01_direct_replay import EXPECTED_OUTCOMES, OPEN_STATUS, aggregate
from run_com_01_direct_replay import _extract_archive, _safe_archived_file


def replay(run_id: str, nonce: str) -> dict:
    return {
        "schema": "sipi.com-01-direct-replay.v1",
        "status": OPEN_STATUS,
        "source_mode": "git_archive_at_immutable_commit",
        "run_id": run_id,
        "fresh_run_nonce": nonce,
        "candidate": {"commit": "candidate"},
        "upstream": {"commit": "upstream"},
        "harness": {"scenario_count": 14},
        "toolchain": {"timeout_seconds": 300},
        "fixtures": [{"role": "primary_xlsx", "sha256": "a" * 64}],
        "outcomes": EXPECTED_OUTCOMES,
        "values_aligned": True,
        "fingerprint_drift_count": 1,
        "scenarios": [{"id": "materialized", "comparison": "values_equal_fingerprint_drift"}],
    }


class Com01ReplayRunnerTests(unittest.TestCase):
    def test_archived_file_rejects_absolute_and_parent_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.xlsx").write_bytes(b"fixture")
            self.assertEqual(_safe_archived_file(root, Path("fixture.xlsx")).read_bytes(), b"fixture")
            for unsafe in (Path("../fixture.xlsx"), Path(r"C:\fixture.xlsx")):
                with self.subTest(unsafe=unsafe), self.assertRaises(RuntimeError):
                    _safe_archived_file(root, unsafe)

    def test_archive_extraction_rejects_parent_traversal(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:") as archive:
            member = tarfile.TarInfo("../escape")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "archive"
            with self.assertRaises(RuntimeError):
                _extract_archive(payload.getvalue(), destination)

    def test_aggregate_preserves_fingerprint_only_open_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            output = root / "aggregate.json"
            first.write_text(json.dumps(replay("run-01", "1" * 64)), encoding="utf-8")
            second.write_text(json.dumps(replay("run-02", "2" * 64)), encoding="utf-8")
            document = aggregate(first, second, output)
        self.assertEqual(document["status"], OPEN_STATUS)
        self.assertEqual(document["blockers"], [])
        self.assertTrue(document["values_aligned"])
        self.assertEqual(document["fingerprint_drift_count"], 1)

    def test_aggregate_rejects_duplicate_nonce_and_outcome_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            output = root / "aggregate.json"
            left = replay("run-01", "1" * 64)
            right = copy.deepcopy(replay("run-02", "1" * 64))
            right["outcomes"] = {"passed": 14}
            first.write_text(json.dumps(left), encoding="utf-8")
            second.write_text(json.dumps(right), encoding="utf-8")
            document = aggregate(first, second, output)
        self.assertEqual(document["status"], "blocked")
        self.assertIn("fresh run nonces must be distinct", document["blockers"])
        self.assertIn("second report outcome inventory drift", document["blockers"])


if __name__ == "__main__":
    unittest.main()
