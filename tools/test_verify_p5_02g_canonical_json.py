"""Tests for the P5-02g canonical parameter JSON v1 verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_02g_canonical_json as GATE


class CanonicalTests(unittest.TestCase):
    def test_current_canonical_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["resolved"], 7)
        self.assertEqual(result["needs_oracle"], 23)

    def test_resolved_chains_carry_literal_values(self) -> None:
        canonical = GATE.load_yaml(GATE.CANONICAL)
        found = 0
        for key, entry in canonical["keys"].items():
            for default in entry["defaults"]:
                if default["kind"] == "resolved_reference":
                    found += 1
                    self.assertIn("value", default, key)
                    self.assertIn("chain", default, key)
        self.assertEqual(found, GATE.RESOLVED_CALLS)

    def test_arithmetic_never_evaluated(self) -> None:
        canonical = GATE.load_yaml(GATE.CANONICAL)
        for key, entry in canonical["keys"].items():
            for default in entry["defaults"]:
                if default["kind"] != "string_literal" and "expression" in default and any(op in default["expression"] for op in ("*", "/", "+", "-")):
                    self.assertEqual(default["kind"], "needs_matlab_oracle", key)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-02g", plan_text)

    def test_rejects_resolution_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        canonical = copy.deepcopy(GATE.load_yaml(GATE.CANONICAL))
        canonical["resolved_default_calls"] = 99
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "canonical.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(canonical, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CANONICAL", tmp_path):
                with self.assertRaises(GATE.CanonicalError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
