"""Tests for the P4B-07c RX init surface exploration verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_07_rx_init_surface_exploration as GATE


class ExplorationTests(unittest.TestCase):
    def test_current_exploration_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["variants"], 4)

    def test_all_variants_crash_reproducibly(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        for variant in GATE.VARIANTS:
            result = evidence["variants"][variant]
            self.assertTrue(result["reproducible"], variant)
            self.assertFalse(result["init_succeeded"], variant)
            self.assertEqual(result["custody_0"]["rc"], 3221225477)
            self.assertEqual(result["custody_1"]["rc"], 3221225477)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P4B-07c", plan_text)

    def test_rejects_unexpected_success(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        evidence = copy.deepcopy(GATE.load_yaml(GATE.EVIDENCE))
        evidence["variants"]["decay"]["init_succeeded"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "evidence.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", tmp_path):
                with self.assertRaises(GATE.ExplorationError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
