"""Tests for the P5-02f canonical parameter JSON draft verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_02f_parameter_json_draft as GATE


class DraftTests(unittest.TestCase):
    def test_current_draft_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["literal_defaults"], 163)
        self.assertEqual(result["reference_defaults"], 30)

    def test_draft_matches_reference_source(self) -> None:
        draft = GATE.load_yaml(GATE.DRAFT)
        reference = GATE.load_yaml(GATE.REFERENCE)
        self.assertEqual(draft["source_sha256"], reference["source_sha256"])

    def test_literal_defaults_never_evaluated(self) -> None:
        draft = GATE.load_yaml(GATE.DRAFT)
        for key, entry in draft["keys"].items():
            for call in entry["calls"]:
                kind = call["default"]["kind"]
                self.assertIn(kind, ("none", "literal", "inf_literal", "string_literal", "reference", "unclassified"), key)
                if kind in ("literal", "reference", "unclassified"):
                    self.assertTrue(call["default"]["expression"], key)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-02f", plan_text)

    def test_rejects_classification_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        draft = copy.deepcopy(GATE.load_yaml(GATE.DRAFT))
        draft["literal_default_calls"] = 999
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "draft.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(draft, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "DRAFT", tmp_path):
                with self.assertRaises(GATE.DraftError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
