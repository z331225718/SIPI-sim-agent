"""Tests for the P5-06b oracle metric surface verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_06b_oracle_metric_surface as GATE


class SurfaceTests(unittest.TestCase):
    def test_current_surface_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["output_keys"], 14)

    def test_roles_and_keys_observed(self) -> None:
        surface = GATE.load_yaml(GATE.SURFACE)
        self.assertEqual(surface["network_roles"], ["THRU", "FEXT1", "NEXT1"])
        self.assertIn("TXLE_taps", surface["checkpoint_keys"])
        self.assertIn("DFE_taps", surface["checkpoint_keys"])

    def test_summary_hash_bound(self) -> None:
        surface = GATE.load_yaml(GATE.SURFACE)
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(surface["source_sha256"], evidence["output_file_hashes"]["summary.json"])

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-06b", plan_text)

    def test_rejects_key_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        surface = copy.deepcopy(GATE.load_yaml(GATE.SURFACE))
        surface["output_metric_keys"].append("EXTRA")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "surface.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(surface, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "SURFACE", tmp_path):
                with self.assertRaises(GATE.SurfaceError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
