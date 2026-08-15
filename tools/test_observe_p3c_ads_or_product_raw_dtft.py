from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("or_raw_observer", ROOT / "tools/observe_p3c_ads_or_product_raw_dtft.py")
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class OriginalRawObserverTests(unittest.TestCase):
    def test_inventory_is_exactly_the_external_chain(self) -> None:
        self.assertEqual({item.as_posix() for item in OBSERVER.INVENTORY}, {"tools/run_p3c_external_ads_original_product_raw_dtft.py", "tools/extract_p3c_ads_pre_final_common_nodes.py", "crates/sipi-p3c/tests/p3c_ads_or_product_raw_dtft_runner.rs", "tools/observe_p3c_ads_or_product_raw_dtft.py"})

    def test_product_report_rejects_unknown_shape(self) -> None:
        path = ROOT / "target" / "or-product-raw-invalid.json"; path.parent.mkdir(exist_ok=True); path.write_text(json.dumps({"schema": "wrong"}), encoding="ascii")
        try:
            with self.assertRaisesRegex(OBSERVER.ObservationError, "product_report_shape"):
                OBSERVER.read_product_report(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
