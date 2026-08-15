from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("original_raw_dtft", ROOT / "tools/run_p3c_external_ads_original_product_raw_dtft.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class OriginalProductRawRunnerTests(unittest.TestCase):
    def test_reuses_the_pinned_ads_dataset_api(self) -> None:
        self.assertEqual(RUNNER.COMMON.ADS_PYTHON, Path(r"C:\Program Files\Keysight\ADS2026_Update1\tools\python\python.exe"))
        self.assertEqual(RUNNER.COMMON.PYTHON_ID[0], 91_136)
        self.assertEqual(RUNNER.COMMON.DOC_ID[0], 62_006)

    def test_only_the_or_payload_export_is_requested(self) -> None:
        self.assertEqual(RUNNER.COMMON.EXTRACTOR.name, "extract_p3c_ads_pre_final_common_nodes.py")
        self.assertEqual(RUNNER.export_or_hdiff.__name__, "export_or_hdiff")


if __name__ == "__main__":
    unittest.main()
