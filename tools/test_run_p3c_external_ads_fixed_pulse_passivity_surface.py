from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("passivity_surface", ROOT / "tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py")
assert SPEC and SPEC.loader
SURFACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SURFACE)


class PassivitySurfaceTests(unittest.TestCase):
    def test_only_documented_output_request_differs_from_fixed_pulse_predecessor(self) -> None:
        netlist = SURFACE.build_netlist()
        SURFACE.assert_fixed_output_only_delta(netlist)
        self.assertEqual(netlist.count("ImpSaveSpectrum=yes"), 1)
        self.assertIn("ImpEnforcePassivity=yes ImpSaveSpectrum=yes", netlist)

    def test_vectorset_allowlist_is_exact_and_has_all_s0_matrix_members(self) -> None:
        names = SURFACE.expected_vectorsets()
        self.assertEqual(len(names), 65)
        self.assertEqual(sum(".CMP1_S0(" in name for name in names), 16)
        self.assertEqual(names[-1], "TRAN.TRAN")
        self.assertEqual(
            SURFACE.canonical_vectorset_identity(names),
            "d8a2e18a8237e81b7f0ce559b26116bae2aa82b5672a54e81a948bb8c07b3087",
        )


if __name__ == "__main__":
    unittest.main()
