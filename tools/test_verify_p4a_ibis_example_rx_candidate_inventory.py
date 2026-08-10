"""Unit tests for bounded, observer-only P4A example_rx inventory parsing."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_inventory", ROOT / "tools" / "verify_p4a_ibis_example_rx_candidate_inventory.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


SAMPLE = b"""[IBIS Ver] 7.1
[Component] Example_Rx
[Package]
[Pin]
1p Sig model_a
[Model] model_a
Model_type Input
C_comp 1p 1p 1p
[Algorithmic Model]
Executable Windows_VisualStudio_64 model_a_x64.dll model_a.ami
[End Algorithmic Model]
[Temperature_Range] 25 0 100
[Voltage_Range] 1.8 1.6 2.0
[GND Clamp]
0 0 0 0
[Power Clamp]
0 0 0 0
[END]
"""


class IbisExampleInventoryTests(unittest.TestCase):
    def test_extracts_only_bounded_inventory_facts(self) -> None:
        observed = GATE.parse_ibis_observation(SAMPLE)
        self.assertEqual(observed["ibis_version"], "7.1")
        self.assertEqual(observed["models"], [{"name": "model_a", "model_type": "Input"}])
        self.assertEqual(observed["pin_model_selectors"], ["model_a"])
        self.assertEqual(observed["table_families"], ["GND Clamp", "Power Clamp"])
        self.assertEqual(observed["algorithmic_executables"][0]["dll_name"], "model_a_x64.dll")

    def test_rejects_missing_model_or_binding_metadata(self) -> None:
        with self.assertRaises(GATE.InventoryError):
            GATE.parse_ibis_observation(b"[IBIS Ver] 7.1\n[Component] X\n")
        with self.assertRaises(GATE.InventoryError):
            GATE.parse_ibis_observation(SAMPLE.replace(b"[Pin]", b"[Pins]"))

    def test_static_scope_validator_rejects_promotion_or_binding_upgrade(self) -> None:
        manifest = {
            "schema": GATE.SCHEMA,
            "status": "candidate_not_required_preflight_passed",
            "promotion_eligible": False,
            "profile": {"id": GATE.PROFILE_ID, "required_by": None, "boundary": "oracle_only"},
            "ibis_observation": {"table_families": ["GND Clamp", "Power Clamp"], "models": [{"name": "example_rx", "model_type": "Input"}], "pin_model_selectors": ["example_rx"]},
            "windows_x64_asset_binding": {"status": "blocked_declared_filename_not_authorized_asset_name"},
        }
        GATE.validate_static_scope(manifest)
        upgraded = copy.deepcopy(manifest)
        upgraded["promotion_eligible"] = True
        with self.assertRaises(GATE.InventoryError):
            GATE.validate_static_scope(upgraded)
        upgraded = copy.deepcopy(manifest)
        upgraded["windows_x64_asset_binding"]["status"] = "name_matched_not_runtime_verified"
        with self.assertRaises(GATE.InventoryError):
            GATE.validate_static_scope(upgraded)


if __name__ == "__main__":
    unittest.main()
