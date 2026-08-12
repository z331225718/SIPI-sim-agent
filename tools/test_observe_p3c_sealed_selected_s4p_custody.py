"""Focused tests for P3C external sealed-S4P custody report parsing."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_sealed_s4p_observer", ROOT / "tools" / "observe_p3c_sealed_selected_s4p_custody.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def report(first: str = "a" * 64, second: str = "b" * 64, count: int = 1025) -> dict:
    return {
        "schema": MODULE.RUNNER_SCHEMA,
        "status": "observed",
        "source_byte_length": MODULE.SOURCE_LENGTH,
        "source_sha256": MODULE.SOURCE_SHA256,
        "source_identity_checks": "before_stage_after_equal",
        "fresh_runs": [
            {"manifest_sha256": first, "record_count": count},
            {"manifest_sha256": second, "record_count": count},
        ],
        "cleanup_status": "complete",
    }


class P3cSealedS4pCustodyObserverTests(unittest.TestCase):
    def parse(self, value: dict) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runner.json"
            path.write_text(json.dumps(value), encoding="ascii")
            return MODULE.parse_runner_report(path)

    def test_accepts_two_distinct_positive_runs(self) -> None:
        self.assertEqual(self.parse(report())["fresh_runs"][0]["record_count"], 1025)

    def test_rejects_reused_manifest_or_count_mismatch(self) -> None:
        with self.assertRaises(MODULE.ObservationError):
            self.parse(report(second="a" * 64))
        with self.assertRaises(MODULE.ObservationError):
            self.parse({**report(), "fresh_runs": [report()["fresh_runs"][0], {"manifest_sha256": "b" * 64, "record_count": 3}]})

    def test_rejects_paths_inside_the_worktree(self) -> None:
        with self.assertRaises(MODULE.ObservationError):
            MODULE.require_external_report(ROOT / "out.json")


if __name__ == "__main__":
    unittest.main()
