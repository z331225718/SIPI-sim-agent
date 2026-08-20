"""Tests for the P5-02i warning observation verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_02i_warning_observation as GATE


class WarningObservationTests(unittest.TestCase):
    def test_current_observation_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["warnings"], 25)

    def test_warning_kinds_are_bounded(self) -> None:
        observation = GATE.load_yaml(GATE.OBSERVATION)
        kinds = {w["kind"] for w in observation["warnings"]}
        self.assertTrue(kinds <= {"warning", "fprintf_strong", "msgbox_warning"})

    def test_source_hash_matches_registry(self) -> None:
        observation = GATE.load_yaml(GATE.OBSERVATION)
        registry = GATE.load_yaml(GATE.REGISTRY)
        material = next(m for m in registry["materials"] if m["id"] == GATE.MATLAB_ID)
        self.assertEqual(observation["source_sha256"], material["sha256"].lower())

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-02i", plan_text)

    def test_rejects_count_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        observation = copy.deepcopy(GATE.load_yaml(GATE.OBSERVATION))
        observation["warning_call_count"] = 99
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "observation.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(observation, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "OBSERVATION", tmp_path):
                with self.assertRaises(GATE.WarningObservationError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
