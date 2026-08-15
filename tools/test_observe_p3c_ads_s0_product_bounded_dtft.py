from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("s0_product_dtft_observer", ROOT / "tools/observe_p3c_ads_s0_product_bounded_dtft.py")
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class S0ProductDtftObserverTests(unittest.TestCase):
    def test_inventory_is_limited_to_ads_export_product_runner_and_observer(self) -> None:
        self.assertEqual(
            {path.as_posix() for path in OBSERVER.INVENTORY},
            {
                "tools/run_p3c_external_ads_prepassivity_product_dtft.py",
                "tools/extract_p3c_ads_pre_final_common_nodes.py",
                "crates/sipi-p3c/tests/p3c_ads_s0_product_bounded_dtft_runner.rs",
                "tools/observe_p3c_ads_s0_product_bounded_dtft.py",
            },
        )

    def test_product_report_rejects_out_of_range_delta_index(self) -> None:
        value = {
            "schema": "sipi.p3c.ads-s0-product-bounded-dtft-runner.v1", "status": "observed", "manifest_sha256": "0" * 64,
            "record_count": 2002, "bounded_sample_count": 51200, "sample_interval_bits": "3d712e0be826d695",
            "causality_iterations": 32, "causality_stop": "successive_error_difference", "ads_s0_payload_byte_length": 1,
            "ads_s0_payload_sha256": "0" * 64, "ads_s0_axis_sha256": "0" * 64, "ads_s0_hdiff_sha256": "0" * 64,
            "product_dtft_sha256": "0" * 64, "delta_sha256": "0" * 64, "delta_l2_squared_bits": "0" * 16,
            "delta_max_abs_bits": "0" * 16, "delta_max_index": 1024, "cleanup_status": "complete",
        }
        path = ROOT / "target" / "s0-product-dtft-invalid.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(__import__("json").dumps(value), encoding="ascii")
        try:
            with self.assertRaisesRegex(OBSERVER.ObservationError, "product_report_count"):
                OBSERVER.read_product_report(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
