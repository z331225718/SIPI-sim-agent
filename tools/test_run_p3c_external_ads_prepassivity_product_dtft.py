from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepassivity_dtft", ROOT / "tools/run_p3c_external_ads_prepassivity_product_dtft.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class PrepassivityDtftRunnerTests(unittest.TestCase):
    def test_reuses_the_common_node_dataset_api_identity(self) -> None:
        self.assertEqual(RUNNER.COMMON.ADS_PYTHON, Path(r"C:\Program Files\Keysight\ADS2026_Update1\tools\python\python.exe"))
        self.assertEqual(RUNNER.COMMON.PYTHON_ID[0], 91_136)
        self.assertEqual(RUNNER.COMMON.DOC_ID[0], 62_006)

    def test_payload_is_named_as_a_reduced_prepassivity_surface(self) -> None:
        self.assertEqual(RUNNER.COMMON.EXTRACTOR.name, "extract_p3c_ads_pre_final_common_nodes.py")


if __name__ == "__main__":
    unittest.main()
