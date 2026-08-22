from __future__ import annotations

import copy
import unittest

from tools import verify_upstream_migration_inventory as gate


class UpstreamMigrationInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = gate._load(gate.INVENTORY)
        self.release = gate._load(gate.RELEASE)
        self.reconciliation = gate._load(gate.RECONCILIATION)

    def validate(self, inventory=None, release=None, reconciliation=None):
        return gate.validate(
            inventory=self.inventory if inventory is None else inventory,
            release=self.release if release is None else release,
            reconciliation=self.reconciliation if reconciliation is None else reconciliation,
        )

    def test_current_inventory_is_active_and_open(self) -> None:
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["migration_rows"], 15)
        self.assertEqual(result["release_blockers"], 9)

    def test_new_feature_freeze_cannot_be_removed(self) -> None:
        mutated = copy.deepcopy(self.inventory)
        mutated["feature_policy"]["new_domain_features_allowed"] = True
        with self.assertRaisesRegex(gate.InventoryError, "new_feature_freeze_removed"):
            self.validate(inventory=mutated)

    def test_self_test_cannot_promote_parity(self) -> None:
        mutated = copy.deepcopy(self.inventory)
        mutated["entries"][0]["parity_status"] = "accepted"
        with self.assertRaisesRegex(gate.InventoryError, "unsubstantiated_parity"):
            self.validate(inventory=mutated)

    def test_missing_upstream_workflow_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.inventory)
        mutated["entries"].pop()
        with self.assertRaisesRegex(gate.InventoryError, "migration_entry_set_invalid"):
            self.validate(inventory=mutated)

    def test_release_item_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.release)
        mutated["items"][0]["status"] = "accepted"
        with self.assertRaisesRegex(gate.InventoryError, "release_item_promoted"):
            self.validate(release=mutated)

    def test_historical_item_cannot_disappear_from_reconciliation(self) -> None:
        mutated = copy.deepcopy(self.reconciliation)
        del mutated["mappings"]["P5-06"]
        with self.assertRaisesRegex(gate.InventoryError, "reconciliation_mapping_set_invalid"):
            self.validate(reconciliation=mutated)

    def test_mapping_cannot_point_to_unknown_target(self) -> None:
        mutated = copy.deepcopy(self.reconciliation)
        mutated["mappings"]["P3B-02"] = ["PB-99"]
        with self.assertRaisesRegex(gate.InventoryError, "reconciliation_target_invalid"):
            self.validate(reconciliation=mutated)


if __name__ == "__main__":
    unittest.main()
