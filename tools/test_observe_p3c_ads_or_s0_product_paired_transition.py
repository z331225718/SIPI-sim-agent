from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("paired_observer", ROOT / "tools/observe_p3c_ads_or_s0_product_paired_transition.py")
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class PairedTransitionObserverTests(unittest.TestCase):
    def test_inventory_is_exactly_the_external_export_and_runner_closure(self) -> None:
        self.assertEqual(
            {path.as_posix() for path in OBSERVER.INVENTORY},
            {
                "tools/run_p3c_external_ads_or_s0_paired_transition.py",
                "tools/extract_p3c_ads_pre_final_common_nodes.py",
                "crates/sipi-p3c/tests/p3c_ads_or_s0_product_paired_transition_runner.rs",
                "tools/observe_p3c_ads_or_s0_product_paired_transition.py",
            },
        )

    def test_product_report_rejects_out_of_range_first_maximum_index(self) -> None:
        value = {
            "schema": "sipi.p3c.ads-or-s0-product-error-decomposition-runner.v1", "status": "observed", "manifest_sha256": "0" * 64,
            "record_count": 2002, "common_node_count": 1024, "sample_interval_bits": "3d712e0be826d695", "raw_sample_count": 51200, "bounded_sample_count": 51200,
            "causality_iterations": 32, "causality_stop": "successive_error_difference", "ads_payload_byte_length": 1, "ads_payload_sha256": "0" * 64,
            "axis_sha256": "0" * 64, "ads_original_sha256": "0" * 64, "ads_s0_sha256": "0" * 64, "product_raw_sha256": "0" * 64, "product_bounded_sha256": "0" * 64,
            "ads_transition_sha256": "0" * 64, "product_transition_sha256": "0" * 64, "paired_delta_sha256": "0" * 64, "pre_delta_sha256": "0" * 64, "post_delta_sha256": "0" * 64, "closure_residual_sha256": "0" * 64,
            "pre_delta_l2_squared_bits": "0" * 16, "pre_delta_max_abs_bits": "0" * 16, "pre_delta_max_index": 0, "post_delta_l2_squared_bits": "0" * 16, "post_delta_max_abs_bits": "0" * 16, "post_delta_max_index": 0,
            "paired_delta_l2_squared_bits": "0" * 16, "paired_delta_max_abs_bits": "0" * 16, "paired_delta_max_index": 1024, "cross_term_bits": "0" * 16, "closure_residual_l2_squared_bits": "0" * 16, "closure_residual_max_abs_bits": "0" * 16, "closure_residual_max_index": 0, "cleanup_status": "complete",
        }
        path = ROOT / "target" / "paired-transition-invalid.json"; path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(value), encoding="ascii")
        try:
            with self.assertRaisesRegex(OBSERVER.ObservationError, "product_report_count"):
                OBSERVER.read_product(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
