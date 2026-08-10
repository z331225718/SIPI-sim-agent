from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_ibis_input_typ_static", ROOT / "tools" / "verify_p4a_ibis_input_typ_static_acceptance.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class AcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs" / "baselines" / "p4a-ibis-input-typ-static-acceptance.v1.yaml").read_text(encoding="utf-8"))

    def test_selected_external_profile_is_valid_without_asset_bytes(self) -> None:
        report = GATE.validate(self.document)
        self.assertTrue(report["valid"])
        self.assertEqual(report["status"], "required_pending_i_v_compare")

    def test_rejects_hidden_profile_scope_or_tolerance_drift(self) -> None:
        for mutate in (
            lambda value: value["profile"].update({"package_scope": "typical_package"}),
            lambda value: value["comparison"].update({"out_of_domain": "clamp"}),
            lambda value: value["stimulus"].update({"timebase": "1ps"}),
        ):
            document = copy.deepcopy(self.document)
            mutate(document)
            with self.assertRaises(ValueError):
                GATE.validate(document)


if __name__ == "__main__":
    unittest.main()
