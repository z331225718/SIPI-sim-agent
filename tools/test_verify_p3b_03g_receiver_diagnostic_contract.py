"""Tests for the P3B-03g receiver diagnostic contract gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3b_03g_receiver_diagnostic_contract as GATE


class DiagnosticContractTests(unittest.TestCase):
    def test_current_contract_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["markers"], 5)

    def test_route_wired_in_manifest(self) -> None:
        text = GATE.read_text(GATE.CLI_MAIN)
        self.assertIn("link.receiver.run", text)
        self.assertIn("fn link_receiver_run_stdin", text)

    def test_all_markers_present_in_cli_source(self) -> None:
        text = GATE.read_text(GATE.CLI_MAIN)
        for marker in GATE.EXPECTED_MARKERS:
            self.assertIn(marker, text, f"missing marker {marker}")

    def test_schemas_bound(self) -> None:
        cli = GATE.read_text(GATE.CLI_MAIN)
        contracts = GATE.read_text(GATE.CONTRACTS)
        for schema in GATE.EXPECTED_SCHEMAS:
            self.assertTrue(schema in cli or schema in contracts, f"missing schema {schema}")

    def test_profile_bound(self) -> None:
        cli = GATE.read_text(GATE.CLI_MAIN)
        contracts = GATE.read_text(GATE.CONTRACTS)
        self.assertIn(GATE.EXPECTED_PROFILE, cli + contracts)

    def test_no_promotion_markers(self) -> None:
        text = GATE.read_text(GATE.CLI_MAIN)
        # The diagnostic must not claim acceptance or external RFM anywhere.
        # Source text escapes JSON quotes as \\"; a promotion would read true.
        self.assertNotIn("acceptance\\\\\\\":true", text)
        self.assertNotIn("external_rfm\\\\\\\":true", text)


if __name__ == "__main__":
    unittest.main()