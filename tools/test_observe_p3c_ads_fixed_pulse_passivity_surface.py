from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("passivity_observer", ROOT / "tools/observe_p3c_ads_fixed_pulse_passivity_surface.py")
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class PassivityObserverTests(unittest.TestCase):
    def test_fixed_surface_is_only_the_documented_pre_correction_inventory(self) -> None:
        self.assertEqual(OBSERVER.EXPECTED_SURFACE["vectorset_count"], 65)
        self.assertEqual(OBSERVER.EXPECTED_SURFACE["s0_vectorset_count"], 16)
        self.assertEqual(len(OBSERVER.EXPECTED_SURFACE["vectorset_identity_sha256"]), 64)

    def test_only_allowlisted_runner_sources_enter_clean_archive_inventory(self) -> None:
        self.assertEqual(
            {path.as_posix() for path in OBSERVER.INVENTORY},
            {
                "tools/run_p3c_external_ads_fixed_pulse_operator.py",
                "tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py",
                "tools/observe_p3c_ads_fixed_pulse_passivity_surface.py",
            },
        )


if __name__ == "__main__":
    unittest.main()
