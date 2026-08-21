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

import verify_p3c_02_waveform_only_supersession as GATE


class P3C02WaveformOnlySupersessionTests(unittest.TestCase):
    def _mutate(self, mutation) -> None:
        document = copy.deepcopy(GATE._load(GATE.EVIDENCE))
        mutation(document)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.yaml"
            path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", path):
                with self.assertRaises(GATE.P3C02SupersessionError):
                    GATE.validate(ROOT)

    def test_current_record_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertTrue(result["current_route_closed"])

    def test_rejects_receiver_promotion(self) -> None:
        self._mutate(lambda value: value["owner_decision"].update(receiver="ctle"))

    def test_rejects_eye_reintroduction(self) -> None:
        self._mutate(lambda value: value["owner_decision"].update(excluded_observables=["TIE", "bathtub"]))

    def test_rejects_acceptance_promotion(self) -> None:
        self._mutate(lambda value: value["selected_route_core"].update(acceptance_ready=True))

    def test_rejects_reference_hash_mutation(self) -> None:
        self._mutate(lambda value: value["supersession"].update(prior_gap_sha256="0" * 64))


if __name__ == "__main__":
    unittest.main()
