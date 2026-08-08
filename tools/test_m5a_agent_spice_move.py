"""Focused checks for the M5A-07 migration verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import verify_m5a_agent_spice_move as verifier  # noqa: E402


class M5AAgentSpiceMoveTests(unittest.TestCase):
    def test_rejects_non_pe_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a PE image"):
            verifier._normalize_pe_build_metadata(b"not an executable")

    def test_repository_move_evidence_is_ready(self) -> None:
        report = verifier.verify(TOOLS.parent)
        self.assertTrue(report["ready"], report["blockers"])


if __name__ == "__main__":
    unittest.main()
