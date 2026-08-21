from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_02_current_semantics_gap as GATE


class P3C02GapTests(unittest.TestCase):
    def test_current_gap_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["blocker_count"], 4)
        self.assertFalse(result["source_port_admitted"])
        self.assertFalse(result["acceptance_ready"])

    def test_owner_boundary_is_waveform_only(self) -> None:
        document = GATE._load(GATE.EVIDENCE)
        owner = document["owner_scope"]
        self.assertEqual(owner["excluded_observables"], ["eye", "TIE", "bathtub"])
        self.assertEqual(owner["scope"], "waveform_only")

    def test_rejects_owner_scope_promotion(self) -> None:
        document = copy.deepcopy(GATE._load(GATE.EVIDENCE))
        document["owner_scope"]["scope"] = "eye_and_bathtub"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.yaml"
            path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", path):
                with self.assertRaises(GATE.P3C02GapError):
                    GATE.validate(ROOT)

    def test_rejects_source_port_admission(self) -> None:
        document = copy.deepcopy(GATE._load(GATE.EVIDENCE))
        document["original_source_observation"]["source_port_admitted"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.yaml"
            path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", path):
                with self.assertRaises(GATE.P3C02GapError):
                    GATE.validate(ROOT)

    def test_rejects_audit_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "audit.md"
            path.write_text("mutated\n", encoding="utf-8")
            with mock.patch.object(GATE, "AUDIT_PATH", "audit.md"):
                with mock.patch.object(GATE, "ROOT", Path(temporary)):
                    with self.assertRaises(GATE.P3C02GapError):
                        GATE.validate(Path(temporary))


if __name__ == "__main__":
    unittest.main()
