"""Tests for the P4B-03 standard ABI host slice gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_03_standard_abi_host_slice as GATE


class HostSliceTests(unittest.TestCase):
    def test_current_slice_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["exports"], 3)

    def test_host_library_present_with_exports(self) -> None:
        lib = GATE.read_text(GATE.HOST_LIB)
        for export in GATE.REQUIRED_EXPORTS:
            self.assertIn(export, lib)

    def test_acceptance_audit_tracked(self) -> None:
        audit = GATE.read_text(GATE.ACCEPTANCE_AUDIT)
        for token in GATE.REQUIRED_CONTRACT_TOKENS:
            self.assertIn(token, audit)

    def test_audit_does_not_claim_vendor_interop(self) -> None:
        audit = GATE.read_text(GATE.ACCEPTANCE_AUDIT)
        self.assertIn("not a claim of vendor", audit)

    def test_files_tracked(self) -> None:
        self.assertTrue(GATE.git_tracked(GATE.HOST_LIB), GATE.HOST_LIB)
        self.assertTrue(GATE.git_tracked(GATE.ACCEPTANCE_AUDIT), GATE.ACCEPTANCE_AUDIT)


if __name__ == "__main__":
    unittest.main()
