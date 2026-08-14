from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("delta", ROOT / "tools/verify_p3c_selected_causality_transfer_delta_observation.py")
assert SPEC and SPEC.loader
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)


class Tests(unittest.TestCase):
    def test_valid_and_mutations(self) -> None:
        document = yaml.safe_load((ROOT / "docs/baselines/p3c-selected-causality-transfer-delta-observation.v1.yaml").read_text(encoding="utf-8"))
        self.assertTrue(V.verify(document)["valid"])
        for path, value in ((["admission", "causality_policy_changed"], True), (["external_observation", "residual_peak_frequency_bracket", 0, "index"], 204), (["fixed_observation", "dft", "factorization"], [2, 2]), (["external_observation", "bands", 3, "delta_energy_bits"], "0" * 16)):
            changed = copy.deepcopy(document)
            cursor = changed
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            with self.assertRaises(V.VerificationError):
                V.verify(changed, current=False)


if __name__ == "__main__":
    unittest.main()
