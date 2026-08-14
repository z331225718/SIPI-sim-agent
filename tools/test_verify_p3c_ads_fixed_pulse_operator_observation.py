from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pulse", ROOT / "tools/verify_p3c_ads_fixed_pulse_operator_observation.py")
assert SPEC and SPEC.loader
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)


class Tests(unittest.TestCase):
    def test_valid_and_mutations(self) -> None:
        document = yaml.safe_load((ROOT / "docs/baselines/p3c-ads-fixed-pulse-operator-observation-evidence.v1.yaml").read_text(encoding="utf-8"))
        self.assertTrue(V.verify(document)["valid"])
        for path, value in ((["external_observation", "post_pulse_nrmse_bits"], "0" * 16), (["fixed_observation", "pulse", "start_index"], 16352), (["admission", "candidate_waveform_accepted"], True), (["external_observation", "strict_identity"], True)):
            changed = copy.deepcopy(document)
            cursor = changed
            for key in path[:-1]: cursor = cursor[key]
            cursor[path[-1]] = value
            with self.assertRaises(V.VerificationError): V.verify(changed, current=False)


if __name__ == "__main__":
    unittest.main()
