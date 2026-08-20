"""Tests for the P0/P1 foundation gate coverage verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p1_foundation_gate_coverage as GATE


class FoundationTests(unittest.TestCase):
    def test_all_five_verifiers_present(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["verifiers"], 5)

    def test_each_verifier_mapped(self) -> None:
        expected = {"product_boundary", "clean_room_register", "release_license_preflight", "rust_candidate_source_map", "acceptance_profiles"}
        self.assertEqual(set(GATE.FOUNDATION_VERIFIERS), expected)

    def test_all_verifiers_exist_on_disk(self) -> None:
        for name, relative in GATE.FOUNDATION_VERIFIERS.items():
            self.assertTrue((ROOT / relative).is_file(), f"{name}: {relative}")

    def test_all_verifiers_git_tracked(self) -> None:
        for name, relative in GATE.FOUNDATION_VERIFIERS.items():
            self.assertTrue(GATE.git_tracked(relative), f"{name}: {relative}")


if __name__ == "__main__":
    unittest.main()
