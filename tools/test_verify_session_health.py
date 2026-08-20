"""Tests for the session health check tool."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_session_health as GATE


class SessionHealthTests(unittest.TestCase):
    def test_check_list_is_well_formed(self) -> None:
        checks = GATE.check_list()
        self.assertGreaterEqual(len(checks), 6)
        for check in checks:
            self.assertTrue((ROOT / check["tool"]).is_file(), check["tool"])

    def test_health_run_reports_valid(self) -> None:
        report = GATE.run_health()
        self.assertTrue(report["valid"], report)
        self.assertEqual(report["failed"], 0)


if __name__ == "__main__":
    unittest.main()
