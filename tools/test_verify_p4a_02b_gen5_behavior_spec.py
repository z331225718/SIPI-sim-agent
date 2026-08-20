# -*- coding: utf-8 -*-
"""Tests for the P4A-02b Gen5 behavior-spec observation verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4a_02b_gen5_behavior_spec as GATE


class BehaviorSpecTests(unittest.TestCase):
    def test_current_observation_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_profile_hashes(self) -> None:
        observation = GATE.load_yaml(GATE.OBSERVATION)
        self.assertEqual(observation["profile"]["sha256"], GATE.IBS_SHA256)

    def test_two_models_tx_rx(self) -> None:
        observation = GATE.load_yaml(GATE.OBSERVATION)
        models = observation["profile"]["models"]
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0]["model"], "pcie_tx")
        self.assertEqual(models[1]["model"], "pcie_rx")

    def test_tx_rx_probe_status(self) -> None:
        observation = GATE.load_yaml(GATE.OBSERVATION)
        behavior = observation["behavior_spec_observation"]
        self.assertEqual(behavior["tx_model"]["probe_status"], "success_all")
        self.assertEqual(behavior["rx_model"]["probe_status"], "probe_crash_all")

    def test_plan_row_present(self) -> None:
        self.assertIn("**P4A-02b", GATE.PLAN.read_text(encoding="utf-8"))

    def test_no_runtime_admission(self) -> None:
        observation = GATE.load_yaml(GATE.OBSERVATION)
        self.assertFalse(observation["semantic_boundary"]["product_runtime_incurs"])

    def test_rejects_dll_identity_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        observation = copy.deepcopy(GATE.load_yaml(GATE.OBSERVATION))
        observation["behavior_spec_observation"]["dll_identity_status"] = "blocked"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "obs.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(observation, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "OBSERVATION", tmp_path):
                with self.assertRaises(GATE.BehaviorSpecError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()