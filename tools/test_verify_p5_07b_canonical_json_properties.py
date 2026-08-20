"""Tests for the P5-07b canonical JSON property surface verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_07b_canonical_json_properties as GATE


class PropertyTests(unittest.TestCase):
    def test_current_property_surface_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["calls"], 229)

    def test_zero_failures(self) -> None:
        document = GATE.load_yaml(GATE.PROPERTY)
        self.assertEqual(document["properties"]["failures"], [])

    def test_source_hash_matches_v2(self) -> None:
        document = GATE.load_yaml(GATE.PROPERTY)
        v2 = GATE.load_yaml(GATE.V2)
        self.assertEqual(document["source_sha256"], v2["source_sha256"])

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-07b", plan_text)

    def test_rejects_failed_properties(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        document = copy.deepcopy(GATE.load_yaml(GATE.PROPERTY))
        document["properties"]["failures"] = ["bad_kind:x"]
        document["properties"]["pass"] = False
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "property.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "PROPERTY", tmp_path):
                with self.assertRaises(GATE.PropertyError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
