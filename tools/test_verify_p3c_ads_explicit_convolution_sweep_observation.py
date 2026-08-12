from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_explicit_sweep_gate", ROOT / "tools" / "verify_p3c_ads_explicit_convolution_sweep_observation.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class ExplicitConvolutionSweepVerifierTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-ads-explicit-convolution-sweep-observation.v1.yaml").read_text(encoding="utf-8"))

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_sweep_and_candidate_drift(self) -> None:
        document = self.document()
        document["sweep"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.VerificationError, "tool_binding"):
            GATE.verify(document)
        document = self.document()
        document["candidates"][2]["third_period_nrmse"] = 0.02
        with self.assertRaisesRegex(GATE.VerificationError, "candidates"):
            GATE.verify(document)

    def test_rejects_product_promotion_or_lost_policy_blocker(self) -> None:
        document = self.document()
        document["admission"]["product_executor_implemented"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion"):
            GATE.verify(document)
        document = copy.deepcopy(self.document())
        document["blockers"].remove("product_output_strobe_mapping_missing")
        with self.assertRaisesRegex(GATE.VerificationError, "product_policy_blocker"):
            GATE.verify(document)

    def test_external_custody_guard_includes_every_waveform_payload(self) -> None:
        hashes = GATE.external_custody_hashes()
        self.assertEqual(len(hashes), 14)
        self.assertIn(GATE.REPORT_SHA256, hashes)
        self.assertIn(GATE.SOURCE_SHA256, hashes)
        self.assertIn("5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", hashes)
        self.assertIn("7a73a5d2fa12944ec7bcde21906bc767734651cf6c622dd08ccf134abe864273", hashes)


if __name__ == "__main__":
    unittest.main()
