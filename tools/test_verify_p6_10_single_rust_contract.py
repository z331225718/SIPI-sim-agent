"""Tests for the P6-10 single-Rust-contract gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p6_10_single_rust_contract as GATE


class SingleContractTests(unittest.TestCase):
    def test_current_invariant_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["patterns_checked"], 4)

    def test_cli_has_no_python(self) -> None:
        text = GATE.read_text(GATE.CLI_MAIN)
        self.assertIsNone(GATE.FORBIDDEN_PATTERNS["python"].search(text))

    def test_cli_has_no_process_spawn(self) -> None:
        text = GATE.read_text(GATE.CLI_MAIN)
        self.assertIsNone(GATE.FORBIDDEN_PATTERNS["process_spawn"].search(text))

    def test_cli_has_no_legacy_fallback(self) -> None:
        text = GATE.read_text(GATE.CLI_MAIN)
        self.assertIsNone(GATE.FORBIDDEN_PATTERNS["legacy_fallback"].search(text))

    def test_cli_main_tracked(self) -> None:
        self.assertTrue(GATE.git_tracked(GATE.CLI_MAIN))


if __name__ == "__main__":
    unittest.main()
