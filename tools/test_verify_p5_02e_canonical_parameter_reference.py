"""Tests for the P5-02e canonical parameter reference verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_02e_canonical_parameter_reference as GATE


class ReferenceTests(unittest.TestCase):
    def test_current_reference_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["keys"], 214)
        self.assertEqual(result["calls"], 229)

    def test_source_hash_matches_registry(self) -> None:
        reference = GATE.load_yaml(GATE.REFERENCE)
        registry = GATE.load_yaml(GATE.REGISTRY)
        material = next(m for m in registry["materials"] if m["id"] == GATE.MATLAB_ID)
        self.assertEqual(reference["source_sha256"], material["sha256"].lower())

    def test_keys_have_call_texts(self) -> None:
        reference = GATE.load_yaml(GATE.REFERENCE)
        for key, entry in reference["keys"].items():
            self.assertTrue(entry["call_texts"], key)
            self.assertTrue(entry["lines"], key)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-02e", plan_text)

    def test_rejects_source_hash_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        reference = copy.deepcopy(GATE.load_yaml(GATE.REFERENCE))
        reference["source_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "reference.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(reference, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "REFERENCE", tmp_path):
                with self.assertRaises(GATE.ReferenceError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
