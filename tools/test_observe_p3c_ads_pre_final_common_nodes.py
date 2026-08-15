from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("common_node_observer", ROOT / "tools/observe_p3c_ads_pre_final_common_nodes.py")
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class CommonNodeObserverTests(unittest.TestCase):
    def test_inventory_is_limited_to_common_node_observation_inputs(self) -> None:
        self.assertEqual(
            {path.as_posix() for path in OBSERVER.INVENTORY},
            {
                "tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py",
                "tools/run_p3c_external_ads_pre_final_common_nodes.py",
                "tools/extract_p3c_ads_pre_final_common_nodes.py",
                "tools/observe_p3c_ads_pre_final_common_nodes.py",
            },
        )

    def test_summary_rejects_untyped_final_only_index(self) -> None:
        malformed = {
            "s0_sha256": "0" * 64,
            "fft_imp_sha256": "0" * 64,
            "delta_sha256": "0" * 64,
            "l2_squared_bits": "0" * 16,
            "max_abs_bits": "0" * 16,
            "max_common_index": 1024,
        }
        with self.assertRaisesRegex(OBSERVER.ObservationError, "common_node_summary_index"):
            OBSERVER.summary(malformed, matrix=False)


if __name__ == "__main__":
    unittest.main()
