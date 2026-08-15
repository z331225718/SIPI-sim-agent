from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_delay_policy_verify", ROOT / "tools" / "verify_p3c_ads_transient_noncausal_delay_policy_surface_observation.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AdsTransientNoncausalDelayPolicyEvidenceTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-ads-transient-noncausal-delay-policy-surface-observation-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_current_evidence_is_valid(self) -> None:
        self.assertTrue(MODULE.verify(self.document())["valid"])

    def test_rejects_cleanup_or_promotion_drift(self) -> None:
        document = self.document()
        document["external_observation"]["cleanup_status"] = "not_complete"
        with self.assertRaisesRegex(MODULE.VerificationError, "evidence_invalid"):
            MODULE.verify(document)
        for field in ("selected_run_delay_action_observed", "delay_seconds_derived", "alignment_authorized", "candidate_waveform_accepted"):
            with self.subTest(field=field):
                document = self.document()
                document["admission"][field] = True
                with self.assertRaisesRegex(MODULE.VerificationError, "evidence_invalid"):
                    MODULE.verify(document)

    def test_rejects_policy_surface_drift(self) -> None:
        document = copy.deepcopy(self.document())
        document["external_observation"]["fixed_pwl_netlist"]["imp_noncausal_length"] = 32
        with self.assertRaisesRegex(MODULE.VerificationError, "evidence_invalid"):
            MODULE.verify(document)


if __name__ == "__main__":
    unittest.main()
