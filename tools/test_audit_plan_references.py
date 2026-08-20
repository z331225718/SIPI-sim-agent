"""Tests for the PLAN reference audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import audit_plan_references as GATE


class PlanReferenceTests(unittest.TestCase):
    def test_all_plan_links_resolve(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertGreater(result["links_checked"], 100)
        self.assertEqual(result["missing"], 0)

    def test_rejects_missing_reference(self) -> None:
        text = GATE.PLAN.read_text(encoding="utf-8") + "\nsee [x](docs/baselines/audits/missing-plan-ref.md)\n"
        with mock.patch.object(GATE, "PLAN", type("FakePath", (), {"read_text": lambda self, encoding: text})()):
            with self.assertRaises(GATE.PlanReferenceError):
                GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
