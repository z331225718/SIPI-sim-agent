"""Tests for the P4A-01 required-profile IBIS inventory verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4a_01_required_profile_inventory as GATE


class P4A01InventoryTests(unittest.TestCase):
    def test_current_inventory_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_inventory_files_present(self) -> None:
        self.assertTrue(GATE.IBS_FILE.is_file())
        self.assertTrue(GATE.INVENTORY.is_file())

    def test_ibis_version_and_component(self) -> None:
        inventory = GATE.load_yaml(GATE.INVENTORY)
        facts = inventory["facts"]
        self.assertEqual(facts["ibis_version"], "5.0")
        self.assertEqual(facts["component"], "AS4C512M16MD4V-053BIN")
        self.assertIn("Model Selector", facts["unique_keywords"])

    def test_model_block_count(self) -> None:
        inventory = GATE.load_yaml(GATE.INVENTORY)
        self.assertEqual(inventory["facts"]["model_block_count"], 67)

    def test_hash_bound(self) -> None:
        import hashlib
        data = GATE.IBS_FILE.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), GATE.EXPECTED_SHA256)
        inventory = GATE.load_yaml(GATE.INVENTORY)
        self.assertEqual(inventory["file"]["sha256"], GATE.EXPECTED_SHA256)

    def test_non_claim_present(self) -> None:
        inventory = GATE.load_yaml(GATE.INVENTORY)
        self.assertIn("not_a_product_ibis_parser", inventory["non_claims"])

    def test_rejects_hash_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        inventory = copy.deepcopy(GATE.load_yaml(GATE.INVENTORY))
        inventory["file"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "inventory.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(inventory, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "INVENTORY", tmp_path):
                with self.assertRaises(GATE.ProfileInventoryError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
