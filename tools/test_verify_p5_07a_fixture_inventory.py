"""Tests for the P5-07a fixture inventory verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_07a_fixture_inventory as GATE


class InventoryTests(unittest.TestCase):
    def test_current_inventory_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["fixtures"], 14)

    def test_manifest_facts_recorded(self) -> None:
        inventory = GATE.load_yaml(GATE.INVENTORY)
        facts = inventory["manifest_facts"]
        self.assertEqual(facts["file_port_order"], ["TX+", "RX+", "TX-", "RX-"])
        self.assertEqual(facts["com_internal_port_order"], ["TX+", "TX-", "RX+", "RX-"])
        self.assertEqual(facts["target_frequency_hz"], 26560000000.0)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-07a", plan_text)

    def test_rejects_fixture_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        inventory = copy.deepcopy(GATE.load_yaml(GATE.INVENTORY))
        inventory["fixture_count"] = 99
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "inventory.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(inventory, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "INVENTORY", tmp_path):
                with self.assertRaises(GATE.InventoryError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
