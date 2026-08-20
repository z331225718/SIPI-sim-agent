"""Tests for the P5-02h canonical parameter JSON v2 verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_02h_canonical_json_v2 as GATE


class V2Tests(unittest.TestCase):
    def test_current_v2_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["evaluated"], 3)
        self.assertEqual(result["needs_oracle"], 20)

    def test_evaluated_values_correct(self) -> None:
        v2 = GATE.load_yaml(GATE.V2)
        found = {}
        for key, entry in v2["keys"].items():
            for default in entry["defaults"]:
                if default["kind"] == "statically_evaluated":
                    found[key] = default["value"]
        self.assertEqual(found.get("N_tc"), "128.0")
        self.assertEqual(found.get("T_h"), "0.0")
        self.assertEqual(found.get("QL"), "0.0")

    def test_grammar_forbids_functions(self) -> None:
        v2 = GATE.load_yaml(GATE.V2)
        self.assertEqual(v2["grammar"]["functions"], "forbidden")

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-02h", plan_text)

    def test_rejects_evaluation_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        v2 = copy.deepcopy(GATE.load_yaml(GATE.V2))
        v2["statically_evaluated_calls"] = 99
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "v2.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(v2, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "V2", tmp_path):
                with self.assertRaises(GATE.V2Error):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
