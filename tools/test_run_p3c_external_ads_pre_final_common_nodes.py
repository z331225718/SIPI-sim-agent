from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("common_node_runner", ROOT / "tools/run_p3c_external_ads_pre_final_common_nodes.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class CommonNodeRunnerTests(unittest.TestCase):
    def test_dataset_api_identities_are_exact(self) -> None:
        self.assertEqual(
            RUNNER.PYTHON_ID,
            (91_136, "8c3fda8eb64fd1ccec107c3903a24060715604cca8b8649743cac5d0df271384"),
        )
        self.assertEqual(
            RUNNER.DOC_ID,
            (62_006, "86577ec72abb6d49926722968043d7b3d639eabc624c031bfd015f827a32894f"),
        )

    def test_common_node_api_is_separate_from_passivity_surface_runner(self) -> None:
        self.assertEqual(RUNNER.EXTRACTOR.name, "extract_p3c_ads_pre_final_common_nodes.py")
        self.assertEqual(RUNNER.SOURCE.name, "run_p3c_external_ads_fixed_pulse_passivity_surface.py")


if __name__ == "__main__":
    unittest.main()
