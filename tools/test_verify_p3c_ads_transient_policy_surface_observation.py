from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_ads_policy", ROOT / "tools" / "verify_p3c_ads_transient_policy_surface_observation.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class AdsTransientPolicySurfaceTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-ads-transient-policy-surface-observation.v1.yaml").read_text(encoding="utf-8"))

    def test_current_observation_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_evidence_or_runner_drift(self) -> None:
        document = self.document()
        document["external_observation"]["report_content_sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.VerificationError, "observation_binding"):
            GATE.verify(document)
        document = self.document()
        document["runner"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.VerificationError, "runner_binding"):
            GATE.verify(document)
        document = self.document()
        document["documentation"]["transient_parameters"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.VerificationError, "documentation_binding"):
            GATE.verify(document)

    def test_rejects_hidden_policy_or_promotion(self) -> None:
        document = copy.deepcopy(self.document())
        document["unresolved_product_policy"].pop()
        with self.assertRaisesRegex(GATE.VerificationError, "unresolved_policy"):
            GATE.verify(document)
        document = self.document()
        document["admission"]["candidate_waveform_generated"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion"):
            GATE.verify(document)

    def test_custody_leak_guard_covers_all_external_documentation(self) -> None:
        self.assertEqual(
            GATE.external_custody_hashes(),
            {
                GATE.REPORT_SHA256,
                GATE.SOURCE_SHA256,
                "94556c3c3a59ee30bb733e92ec795c7d15bb126820e74d57aec9276c7275b667",
                "290ae0dc3771afbbf9e14f326e5b0fc1b131272e10ca96dfbfa3c85193330bca",
                "45372e9c7c79492bf6023a4e860f05a20caf0ef5e2a083407c119909afc187bf",
                "621851d5d3bd754b898c27bccd641da3dae08954ef902f72b6609bd8f093a7e0",
            },
        )


if __name__ == "__main__":
    unittest.main()
