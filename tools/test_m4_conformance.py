from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_m4_conformance import CASES, DOCS, run


class M4ConformanceTests(unittest.TestCase):
    def test_python_conformance_covered_for_all_dtos(self):
        report = run()
        self.assertTrue(report["valid"])
        self.assertEqual(report["python"], "covered")
        self.assertEqual(report["rust"], "deferred")
        self.assertEqual(set(report["schemas"]), set(DOCS))
        for name, entry in report["schemas"].items():
            with self.subTest(schema=name):
                self.assertEqual(entry["python"], "covered")
                self.assertEqual(set(entry["cases"]), set(CASES))
                self.assertTrue(all(entry["cases"].values()))

    def test_committed_record_matches_computed_report(self):
        record = json.loads((ROOT / "docs" / "baselines" / "conformance" / "m4-dto-conformance.json").read_text(encoding="utf-8"))
        report = run()
        self.assertEqual(record, report)


if __name__ == "__main__":
    unittest.main()
