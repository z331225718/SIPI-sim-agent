from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import verify_p1_legacy_fixture_required_profile_facts as GATE


class P1LegacyFixtureRequiredProfileFactsTests(unittest.TestCase):
    def test_current_facts_are_valid(self) -> None:
        result = GATE.validate(GATE._load(GATE.DOCUMENT))
        self.assertTrue(result["valid"])
        self.assertEqual(result["assets"], 14)
        self.assertEqual(result["required_assets"], 9)

    def test_required_by_does_not_become_profile_selection(self) -> None:
        document = GATE._load(GATE.DOCUMENT)
        document["profile_facts"]["required_profile_fields_present"] = True
        with self.assertRaises(GATE.FactsError):
            GATE.validate(document)

    def test_distribution_authorization_is_fail_closed(self) -> None:
        document = copy.deepcopy(GATE._load(GATE.DOCUMENT))
        document["gates"]["distribution_authorized"] = True
        with self.assertRaises(GATE.FactsError):
            GATE.validate(document)


if __name__ == "__main__":
    unittest.main()
