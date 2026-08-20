"""Tests for the P2-03 TRAN semantic freeze verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p2_03_tran_semantic_freeze as GATE


class SemanticFreezeTests(unittest.TestCase):
    def test_current_freeze_is_valid(self) -> None:
        freeze = GATE.load_json(GATE.FREEZE)
        result = GATE.validate(freeze, ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["error_variants"], 20)

    def test_freeze_schema_and_scope(self) -> None:
        freeze = GATE.load_json(GATE.FREEZE)
        self.assertEqual(freeze["schema"], GATE.SCHEMA)
        self.assertEqual(freeze["status"], "provisional")
        self.assertEqual(freeze["scope"], "current_product_surface_only")

    def test_error_taxonomy_matches_live_tran_error_enum(self) -> None:
        library_text = GATE.read_text("crates/sipi-tran/src/lib.rs")
        live = GATE.extract_enum_variants(library_text, "TranError")
        self.assertEqual(live, GATE.EXPECTED_ERROR_VARIANTS)

    def test_freeze_rejects_schema_drift(self) -> None:
        freeze = GATE.load_json(GATE.FREEZE)
        freeze["request_schemas"]["one_node_rc_pulse"] = "sipi.tran.renamed.v1"
        with self.assertRaises(GATE.FreezeError):
            GATE.validate(freeze, ROOT)

    def test_freeze_rejects_error_taxonomy_drift(self) -> None:
        freeze = GATE.load_json(GATE.FREEZE)
        freeze["error_taxonomy"] = ["InvalidResistance"]
        with self.assertRaises(GATE.FreezeError):
            GATE.validate(freeze, ROOT)

    def test_freeze_rejects_device_matrix_drift(self) -> None:
        freeze = GATE.load_json(GATE.FREEZE)
        freeze["device_support_matrix"]["inductor"] = "supported"
        with self.assertRaises(GATE.FreezeError):
            GATE.validate(freeze, ROOT)

    def test_freeze_rejects_resource_limit_drift(self) -> None:
        freeze = GATE.load_json(GATE.FREEZE)
        freeze["solver_policy"]["resource_limits"]["max_output_samples"] = 8192
        with self.assertRaises(GATE.FreezeError):
            GATE.validate(freeze, ROOT)

    def test_freeze_rejects_missing_contract(self) -> None:
        freeze = GATE.load_json(GATE.FREEZE)
        freeze["contract_refs"] = ["docs/clean-room/specs/does-not-exist.v1.md"]
        with self.assertRaises(GATE.FreezeError):
            GATE.validate(freeze, ROOT)

    def test_freeze_binds_live_schemas_and_topologies(self) -> None:
        contracts_text = GATE.read_text("crates/sipi-contracts/src/lib.rs")
        cli_text = GATE.read_text("crates/sipi-cli/src/main.rs")
        for schema in GATE.EXPECTED_SCHEMAS:
            self.assertIn(schema, contracts_text)
        for topology in GATE.EXPECTED_TOPOLOGIES:
            self.assertIn(topology, cli_text)


if __name__ == "__main__":
    unittest.main()
